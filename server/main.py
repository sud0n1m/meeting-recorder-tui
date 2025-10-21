#!/usr/bin/env python3
"""
Meeting Recorder Processing Server
FastAPI server for GPU-accelerated transcription and summarization.
"""

import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import requests

app = FastAPI(
    title="Meeting Recorder Processing Server",
    description="GPU-accelerated transcription and summarization service",
    version="0.4.0"
)

# Global Whisper model (loaded once on startup)
whisper_model: Optional[WhisperModel] = None
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "default")
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")


def load_whisper_model():
    """Load Whisper model on startup."""
    global whisper_model

    print(f"Loading Whisper model '{WHISPER_MODEL_SIZE}'...")
    print(f"  Device: {WHISPER_DEVICE}")
    print(f"  Compute type: {WHISPER_COMPUTE_TYPE}")

    # Detect device
    device = WHISPER_DEVICE
    compute_type = WHISPER_COMPUTE_TYPE

    if device == "auto":
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16" if compute_type == "default" else compute_type
                print(f"  ✓ CUDA GPU detected: {torch.cuda.get_device_name(0)}")
            else:
                device = "cpu"
                compute_type = "int8" if compute_type == "default" else compute_type
                print(f"  ℹ No GPU detected, using CPU")
        except ImportError:
            device = "cpu"
            compute_type = "int8" if compute_type == "default" else compute_type
            print(f"  ℹ PyTorch not installed, using CPU")

    whisper_model = WhisperModel(
        WHISPER_MODEL_SIZE,
        device=device,
        compute_type=compute_type
    )
    print(f"✓ Whisper model loaded successfully on {device} ({compute_type})")


@app.on_event("startup")
async def startup_event():
    """Initialize server on startup."""
    print("="*60)
    print("Meeting Recorder Processing Server v0.4")
    print("="*60)
    load_whisper_model()
    print("\nServer ready! Endpoints:")
    print("  GET  /health")
    print("  POST /api/process")
    print("="*60)


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns 200 if server is ready to process recordings.
    """
    if whisper_model is None:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Model not loaded"}
        )

    return {"status": "ok", "model": WHISPER_MODEL_SIZE}


@app.post("/api/process")
async def process_recording(
    audio: UploadFile = File(...),
    title: str = Form(...),
    whisper_model_override: Optional[str] = Form(None, alias="whisper_model"),
    ollama_model: str = Form("qwen3:8b-q8_0")
):
    """
    Process an audio recording: transcribe with Whisper and summarize with LLM.

    Args:
        audio: Audio file (WAV format)
        title: Meeting title
        whisper_model_override: Override default Whisper model (optional)
        ollama_model: LLM model for summarization

    Returns:
        JSON with transcript and summary
    """
    if whisper_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # Create temp directory for processing
    temp_dir = Path(tempfile.mkdtemp(prefix="meeting_"))

    try:
        # Save uploaded audio
        audio_path = temp_dir / "audio.wav"
        with open(audio_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        print(f"\n{'='*60}")
        print(f"Processing: {title}")
        print(f"Audio size: {len(content) / 1024 / 1024:.1f} MB")
        print(f"{'='*60}")

        # Step 1: Transcribe with Whisper
        print("Transcribing with Whisper...")
        start_time = datetime.now()

        segments, info = whisper_model.transcribe(
            str(audio_path),
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")

        # Build transcript
        transcript_lines = [
            f"# Meeting Transcript: {title}\n",
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        ]

        for segment in segments:
            text = segment.text.strip()
            timestamp = format_timestamp(segment.start)
            line = f"[{timestamp}] {text}\n"
            transcript_lines.append(line)

        transcript = "".join(transcript_lines)
        transcription_time = (datetime.now() - start_time).total_seconds()
        print(f"✓ Transcription completed in {transcription_time:.1f}s")

        # Step 2: Summarize with Ollama
        print(f"Summarizing with {ollama_model}...")
        start_time = datetime.now()

        summary = await summarize_with_ollama(transcript, ollama_model)

        summarization_time = (datetime.now() - start_time).total_seconds()
        print(f"✓ Summarization completed in {summarization_time:.1f}s")

        total_time = transcription_time + summarization_time
        print(f"{'='*60}")
        print(f"✓ Total processing time: {total_time:.1f}s")
        print(f"{'='*60}")

        return {
            "success": True,
            "transcript": transcript,
            "summary": summary,
            "processing_time": total_time,
            "transcription_time": transcription_time,
            "summarization_time": summarization_time
        }

    except Exception as e:
        print(f"❌ Processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


async def summarize_with_ollama(transcript: str, model: str) -> str:
    """
    Summarize transcript using Ollama.

    Args:
        transcript: Full transcript text
        model: Ollama model name

    Returns:
        Summary text
    """
    prompt = f"""Please provide a concise summary of this meeting transcript.

Focus on:
1. Key discussion topics
2. Important decisions made
3. Action items and next steps
4. Notable points raised

Transcript:
{transcript}

Summary:"""

    try:
        response = requests.post(
            f"{OLLAMA_ENDPOINT}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        if response.status_code != 200:
            raise Exception(f"Ollama returned {response.status_code}: {response.text}")

        data = response.json()
        return data.get("response", "Summary generation failed")

    except Exception as e:
        print(f"Warning: Summarization failed: {e}")
        return f"[Summarization failed: {str(e)}]"


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


if __name__ == "__main__":
    import uvicorn

    # Get port from environment or use default
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"\nStarting server on {host}:{port}")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )
