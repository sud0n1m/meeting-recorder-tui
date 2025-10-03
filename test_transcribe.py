#!/usr/bin/env python3
"""Quick test of transcription."""

import time
from pathlib import Path
from src.audio_setup import AudioCaptureSetup
from src.transcribe import Transcriber

# Setup audio
setup = AudioCaptureSetup()

try:
    if not setup.setup():
        print("Failed to setup audio")
        exit(1)

    # Create transcriber
    transcriber = Transcriber(
        model_size="base",
        device="cpu",
        output_dir=Path("./recordings")
    )

    # Load model (this will download it if needed)
    transcriber.load_model()

    # Start recording
    monitor_source = setup.get_monitor_source()
    if not transcriber.start_recording(monitor_source):
        print("Failed to start recording")
        exit(1)

    print("\n🎙️  Recording for 10 seconds... (speak now!)")
    print("Say something like: 'This is a test of the transcription system'\n")

    # Record for 10 seconds
    time.sleep(10)

    # Stop recording
    transcriber.stop_recording()

    # Wait for file to be fully written
    time.sleep(1)

    # Transcribe
    if transcriber.audio_file and transcriber.audio_file.exists():
        print("\n" + "="*60)
        print("TRANSCRIPTION")
        print("="*60)
        transcriber.transcribe_audio(transcriber.audio_file)
        print("\n" + "="*60)
        print(f"Transcript: {transcriber.transcript_file}")
        print(f"Audio: {transcriber.audio_file}")
    else:
        print("No audio recorded")

except KeyboardInterrupt:
    print("\n\nInterrupted")
finally:
    if 'transcriber' in locals():
        transcriber.stop_recording()
    setup.cleanup()
