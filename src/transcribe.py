#!/usr/bin/env python3
"""
Real-time transcription using faster-whisper.
Captures audio from PipeWire and transcribes incrementally.
"""

import subprocess
import threading
import time
import logging
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
from faster_whisper import WhisperModel

# Set up logging
logger = logging.getLogger(__name__)


class Transcriber:
    """Real-time audio transcription with incremental saving."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "default",
        output_dir: Optional[Path] = None
    ):
        """
        Initialize transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (auto, cpu, cuda)
            compute_type: Compute type (default, int8, int8_float16, float16)
            output_dir: Directory to save transcripts (default: current dir)
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.actual_device = None  # Will be set after model load
        self.actual_compute_type = None  # Will be set after model load
        self.output_dir = output_dir or Path.cwd()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.model: Optional[WhisperModel] = None
        self.recording_process: Optional[subprocess.Popen] = None
        self.audio_file_handle = None
        self.transcription_thread: Optional[threading.Thread] = None
        self.running = False

        self.transcript_file: Optional[Path] = None
        self.audio_file: Optional[Path] = None
        self.current_transcript = []

        self.on_segment: Optional[Callable[[str], None]] = None

    def _detect_device_and_compute_type(self):
        """Detect the best device and compute type configuration."""
        device = self.device
        compute_type = self.compute_type

        # Auto-detect device
        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    if compute_type == "default":
                        compute_type = "float16"
                else:
                    device = "cpu"
                    if compute_type == "default":
                        compute_type = "int8"
            except ImportError:
                device = "cpu"
                if compute_type == "default":
                    compute_type = "int8"
        else:
            # Manual device selection
            if compute_type == "default":
                compute_type = "int8" if device == "cpu" else "float16"

        return device, compute_type

    def load_model(self):
        """Load the Whisper model with device detection."""
        device, compute_type = self._detect_device_and_compute_type()

        print(f"Loading Whisper model '{self.model_size}'...")
        print(f"  Device: {device} (requested: {self.device})")
        print(f"  Compute type: {compute_type} (requested: {self.compute_type})")

        try:
            self.model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute_type
            )
            self.actual_device = device
            self.actual_compute_type = compute_type
            print("Model loaded successfully")
        except Exception as e:
            # Fallback to CPU with int8 if GPU fails
            if device != "cpu":
                print(f"Warning: Failed to load on {device}, falling back to CPU")
                print(f"  Error: {e}")
                self.model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8"
                )
                self.actual_device = "cpu"
                self.actual_compute_type = "int8"
                print("Model loaded on CPU")
            else:
                raise

    def get_device_info(self) -> str:
        """Get information about the loaded device."""
        if self.actual_device is None:
            return "Model not loaded"
        return f"{self.actual_device} ({self.actual_compute_type})"

    def start_recording(self, source_name: str) -> bool:
        """
        Start recording audio from PipeWire source.

        Args:
            source_name: PipeWire source to record from

        Returns:
            True if recording started successfully
        """
        if self.running:
            return False

        # Create output files with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.audio_file = self.output_dir / f"recording_{timestamp}.wav"
        self.transcript_file = self.output_dir / f"transcript_{timestamp}.txt"

        print(f"Starting recording from {source_name}")
        print(f"Audio file: {self.audio_file}")
        print(f"Transcript: {self.transcript_file}")

        try:
            # Start recording with parec (PulseAudio/PipeWire recorder)
            # Note: parec outputs raw audio to stdout, so we redirect to file
            self.audio_file_handle = open(self.audio_file, "wb")
            self.recording_process = subprocess.Popen(
                [
                    "parec",
                    "--device", source_name,
                    "--format", "s16le",  # 16-bit signed PCM
                    "--rate", "16000",    # 16kHz (optimal for Whisper)
                    "--channels", "1",     # Mono
                ],
                stdout=self.audio_file_handle,
                stderr=subprocess.PIPE
            )

            self.running = True

            # Initialize transcript file
            self.transcript_file.write_text(
                f"# Meeting Transcript\n"
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )

            return True

        except Exception as e:
            print(f"Error starting recording: {e}")
            return False

    def stop_recording(self):
        """Stop recording audio."""
        print("Stopping recording...")
        self.running = False

        if self.recording_process:
            self.recording_process.terminate()
            self.recording_process.wait(timeout=5)
            self.recording_process = None

        if self.audio_file_handle:
            self.audio_file_handle.close()
            self.audio_file_handle = None

        # Convert raw PCM to WAV format
        if self.audio_file and self.audio_file.exists():
            self._convert_to_wav(self.audio_file)

    def _convert_to_wav(self, raw_file: Path):
        """Convert raw PCM file to WAV format using ffmpeg."""
        try:
            temp_file = raw_file.with_suffix('.raw')
            raw_file.rename(temp_file)

            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "s16le",       # Input format: signed 16-bit little-endian
                    "-ar", "16000",      # Sample rate
                    "-ac", "1",          # Channels: mono
                    "-i", str(temp_file),
                    str(raw_file)        # Output as WAV
                ],
                capture_output=True,
                check=True
            )

            # Remove temp raw file
            temp_file.unlink()
            print(f"Converted to WAV: {raw_file}")

        except Exception as e:
            print(f"Warning: Could not convert to WAV: {e}")

    def transcribe_audio(self, audio_path: Path) -> str:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            Full transcript text
        """
        if not self.model:
            logger.info("Model not loaded, loading now...")
            self.load_model()

        logger.info(f"Transcribing {audio_path}...")
        logger.info(f"  File exists: {audio_path.exists()}")
        if audio_path.exists():
            logger.info(f"  File size: {audio_path.stat().st_size} bytes")

        try:
            segments, info = self.model.transcribe(
                str(audio_path),
                language="en",
                beam_size=5,
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(
                    min_silence_duration_ms=500  # 500ms silence to split segments
                )
            )

            logger.info(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")

            transcript_parts = []
            segment_count = 0

            for segment in segments:
                segment_count += 1
                text = segment.text.strip()
                timestamp = f"[{self._format_timestamp(segment.start)}]"

                # Add to transcript with timestamp
                line = f"{timestamp} {text}\n"
                transcript_parts.append(line)

                # Save incrementally
                self._append_to_file(line)

                # Call callback if set
                if self.on_segment:
                    self.on_segment(text)

                logger.debug(f"{timestamp} {text}")

            logger.info(f"Transcription complete: {segment_count} segments")

            if segment_count == 0:
                logger.warning("No segments transcribed! Audio may be silent or unreadable")

            return "".join(transcript_parts)

        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}", exc_info=True)
            raise

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _append_to_file(self, text: str):
        """Append text to transcript file (incremental saving)."""
        if self.transcript_file:
            with open(self.transcript_file, "a") as f:
                f.write(text)

    def get_transcript_path(self) -> Optional[Path]:
        """Get path to current transcript file."""
        return self.transcript_file

    def get_audio_path(self) -> Optional[Path]:
        """Get path to current audio file."""
        return self.audio_file


def main():
    """Test transcription with a sample recording."""
    import sys
    from audio_setup import AudioCaptureSetup

    # Setup audio
    setup = AudioCaptureSetup()

    try:
        if not setup.setup():
            print("Failed to setup audio")
            return

        # Create transcriber
        transcriber = Transcriber(
            model_size="base",  # Good balance of speed/accuracy
            device="cpu",
            output_dir=Path("./recordings")
        )

        # Load model
        transcriber.load_model()

        # Set up callback for live updates
        def on_segment(text):
            print(f"  [Live] {text}")

        transcriber.on_segment = on_segment

        # Start recording
        monitor_source = setup.get_monitor_source()
        if not transcriber.start_recording(monitor_source):
            print("Failed to start recording")
            return

        print("\n🎙️  Recording... (speak now!)")
        print("Press Ctrl+C to stop\n")

        # Record for duration or until interrupted
        try:
            time.sleep(30)  # Record for 30 seconds
        except KeyboardInterrupt:
            print("\n\nStopping...")

        # Stop recording
        transcriber.stop_recording()

        # Wait a moment for file to be written
        time.sleep(1)

        # Transcribe the recorded audio
        if transcriber.audio_file and transcriber.audio_file.exists():
            print("\n" + "="*60)
            print("TRANSCRIPTION")
            print("="*60)
            transcriber.transcribe_audio(transcriber.audio_file)
            print("\n" + "="*60)
            print(f"\nTranscript saved to: {transcriber.transcript_file}")
        else:
            print("No audio file found to transcribe")

    finally:
        setup.cleanup()


if __name__ == "__main__":
    main()
