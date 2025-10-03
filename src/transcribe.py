#!/usr/bin/env python3
"""
Real-time transcription using faster-whisper.
Captures audio from PipeWire and transcribes incrementally.
"""

import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
from faster_whisper import WhisperModel


class Transcriber:
    """Real-time audio transcription with incremental saving."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        output_dir: Optional[Path] = None
    ):
        """
        Initialize transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (auto, cpu, cuda)
            output_dir: Directory to save transcripts (default: current dir)
        """
        self.model_size = model_size
        self.device = device if device != "auto" else "cpu"  # Default to CPU for now
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

    def load_model(self):
        """Load the Whisper model."""
        print(f"Loading Whisper model '{self.model_size}' on {self.device}...")
        self.model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type="int8"  # Use int8 for faster CPU inference
        )
        print("Model loaded successfully")

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
            self.load_model()

        print(f"\nTranscribing {audio_path}...")

        segments, info = self.model.transcribe(
            str(audio_path),
            language="en",
            beam_size=5,
            vad_filter=True,  # Voice activity detection
            vad_parameters=dict(
                min_silence_duration_ms=500  # 500ms silence to split segments
            )
        )

        print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")

        transcript_parts = []

        for segment in segments:
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

            print(f"{timestamp} {text}")

        return "".join(transcript_parts)

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
