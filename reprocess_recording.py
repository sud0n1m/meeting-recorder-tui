#!/usr/bin/env python3
"""
Re-process a failed or incomplete recording.
Useful for debugging transcription issues or re-running with different settings.
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config
from transcribe import Transcriber
from summarize import Summarizer
from markdown_writer import MarkdownWriter


def reprocess_recording(
    audio_file: Path,
    title: str = None,
    whisper_model: str = None,
    force: bool = False,
    skip_summary: bool = False
):
    """
    Re-process a recording from WAV file.

    Args:
        audio_file: Path to WAV file
        title: Meeting title (optional, extracted from filename if not provided)
        whisper_model: Override Whisper model (optional)
        force: Force reprocessing even if transcript exists
        skip_summary: Skip summarization step
    """
    print("="*60)
    print("Recording Re-processor")
    print("="*60)

    # Validate audio file
    if not audio_file.exists():
        print(f"❌ Error: Audio file not found: {audio_file}")
        return 1

    print(f"\nAudio file: {audio_file}")
    print(f"Size: {audio_file.stat().st_size / 1024 / 1024:.1f} MB")

    # Extract timestamp from filename
    # Format: recording_YYYY-MM-DD_HH-MM-SS.wav
    filename = audio_file.stem  # Remove .wav
    parts = filename.split('_')
    if len(parts) >= 3 and parts[0] == 'recording':
        try:
            date_str = parts[1]
            time_str = parts[2]
            timestamp = datetime.strptime(f"{date_str}_{time_str}", "%Y-%m-%d_%H-%M-%S")
        except:
            timestamp = datetime.now()
    else:
        timestamp = datetime.now()

    # Use title from argument or "Reprocessed"
    if not title:
        title = "Reprocessed"

    print(f"Title: {title}")
    print(f"Timestamp: {timestamp}")

    # Check for existing transcript
    transcript_file = audio_file.parent / f"transcript_{timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    if transcript_file.exists() and not force:
        print(f"\n⚠️  Transcript already exists: {transcript_file}")
        print("Use --force to overwrite")
        response = input("Continue anyway? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted")
            return 0

    # Load config
    config = Config()

    # Override model if specified
    model = whisper_model or config.whisper_model

    print(f"\n{'='*60}")
    print("Step 1: Transcription")
    print(f"{'='*60}")
    print(f"Model: {model}")
    print(f"Device: {config.whisper_device}")
    print(f"Compute type: {config.whisper_compute_type}")

    # Initialize transcriber
    transcriber = Transcriber(
        model_size=model,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        output_dir=audio_file.parent
    )

    # Set the audio file and transcript file
    transcriber.audio_file = audio_file
    transcriber.transcript_file = transcript_file

    # Load model
    print("\nLoading Whisper model...")
    transcriber.load_model()
    print(f"✓ Model loaded on: {transcriber.get_device_info()}")

    # Transcribe
    print("\nTranscribing...")
    try:
        transcript = transcriber.transcribe_audio(audio_file)

        if not transcript or len(transcript.strip()) < 50:
            print(f"\n⚠️  Warning: Transcript is very short or empty")
            print(f"Transcript length: {len(transcript)} characters")
            print("\nPossible issues:")
            print("  - Audio is silent or very quiet")
            print("  - Wrong audio format")
            print("  - Audio is corrupted")
            print("  - Language mismatch (expecting English)")

            # Check if we should continue
            if not skip_summary:
                response = input("\nContinue to summarization anyway? [y/N]: ")
                if response.lower() != 'y':
                    print("Stopped after transcription")
                    return 0

        print(f"✓ Transcription complete")
        print(f"  Transcript file: {transcript_file}")
        print(f"  Lines: {len(transcript.splitlines())}")

    except Exception as e:
        print(f"\n❌ Transcription failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Summarization
    if not skip_summary:
        print(f"\n{'='*60}")
        print("Step 2: Summarization")
        print(f"{'='*60}")
        print(f"Model: {config.ollama_model}")
        print(f"Endpoint: {config.ollama_endpoint}")

        try:
            summarizer = Summarizer(
                model=config.ollama_model,
                endpoint=config.ollama_endpoint
            )
            print("\nSummarizing...")
            summary_path = summarizer.summarize_file(transcript_file)
            print(f"✓ Summary complete")
            print(f"  Summary file: {summary_path}")

        except Exception as e:
            print(f"\n❌ Summarization failed: {e}")
            import traceback
            traceback.print_exc()
            print("\nTranscript was saved successfully, but summary failed")
            return 1

        # Write markdown
        print(f"\n{'='*60}")
        print("Step 3: Markdown Output")
        print(f"{'='*60}")

        try:
            markdown_writer = MarkdownWriter(output_dir=config.meetings_dir)
            markdown_writer.write_meeting(
                transcript_path=transcript_file,
                summary_path=summary_path,
                audio_path=audio_file if config.keep_audio else None,
                timestamp=timestamp,
                title=title
            )
            print(f"✓ Markdown written to: {config.meetings_dir}")

        except Exception as e:
            print(f"\n❌ Markdown writing failed: {e}")
            import traceback
            traceback.print_exc()
            return 1

    print(f"\n{'='*60}")
    print("✓ Reprocessing complete!")
    print(f"{'='*60}")

    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Re-process a failed or incomplete recording",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reprocess a recording
  python reprocess_recording.py recordings/recording_2025-10-21_10-09-16.wav

  # With custom title
  python reprocess_recording.py recordings/recording_2025-10-21_10-09-16.wav --title "Team Meeting"

  # Use larger model for better accuracy
  python reprocess_recording.py recordings/recording_2025-10-21_10-09-16.wav --model medium

  # Force overwrite existing transcript
  python reprocess_recording.py recordings/recording_2025-10-21_10-09-16.wav --force

  # Only transcribe, skip summarization
  python reprocess_recording.py recordings/recording_2025-10-21_10-09-16.wav --skip-summary
        """
    )

    parser.add_argument(
        "audio_file",
        type=Path,
        help="Path to WAV audio file"
    )

    parser.add_argument(
        "-t", "--title",
        type=str,
        help="Meeting title (default: 'Reprocessed')"
    )

    parser.add_argument(
        "-m", "--model",
        type=str,
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model to use (overrides config)"
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force reprocessing even if transcript exists"
    )

    parser.add_argument(
        "--skip-summary",
        action="store_true",
        help="Skip summarization step (only transcribe)"
    )

    args = parser.parse_args()

    try:
        exit_code = reprocess_recording(
            audio_file=args.audio_file,
            title=args.title,
            whisper_model=args.model,
            force=args.force,
            skip_summary=args.skip_summary
        )
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    main()
