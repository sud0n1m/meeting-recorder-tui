#!/usr/bin/env python3
"""
Markdown file writer for meeting notes.
Writes transcripts and summaries to organized directories.
"""

from pathlib import Path
from datetime import datetime
from typing import Optional
import shutil


class MarkdownWriter:
    """Write meeting transcripts and summaries as markdown files."""

    def __init__(self, output_dir: Path):
        """
        Initialize markdown writer.

        Args:
            output_dir: Directory to write meeting files
        """
        self.output_dir = Path(output_dir).expanduser()

        # Create directory structure
        self._ensure_directories()

    def _ensure_directories(self):
        """Create output directory structure if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _format_filename(self, timestamp: datetime, suffix: str) -> str:
        """
        Generate meeting filename.

        Format: YYYY-MM-DD_HH-MM_suffix.md
        Example: 2025-10-03_14-30_transcript.md
        """
        date_str = timestamp.strftime("%Y-%m-%d_%H-%M")
        return f"{date_str}_{suffix}.md"

    def write_transcript(
        self,
        transcript_path: Path,
        timestamp: Optional[datetime] = None,
        title: Optional[str] = None
    ) -> Path:
        """
        Write transcript to output directory.

        Args:
            transcript_path: Path to source transcript file
            timestamp: Meeting timestamp (default: now)
            title: Optional meeting title

        Returns:
            Path to created file
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Read transcript
        transcript_text = transcript_path.read_text()

        # Generate frontmatter
        frontmatter = self._generate_frontmatter(
            timestamp=timestamp,
            doc_type="transcript",
            title=title
        )

        # Create full document
        content = f"{frontmatter}\n# Meeting Transcript\n\n{transcript_text}"

        # Write to output directory
        filename = self._format_filename(timestamp, "transcript")
        output_path = self.output_dir / filename
        output_path.write_text(content)

        print(f"✓ Transcript saved: {output_path}")
        return output_path

    def write_summary(
        self,
        summary_path: Path,
        timestamp: Optional[datetime] = None,
        title: Optional[str] = None,
        transcript_link: Optional[str] = None
    ) -> Path:
        """
        Write summary to output directory.

        Args:
            summary_path: Path to source summary file
            timestamp: Meeting timestamp (default: now)
            title: Optional meeting title
            transcript_link: Link to transcript file

        Returns:
            Path to created file
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Read summary
        summary_text = summary_path.read_text()

        # If summary already has frontmatter, extract it
        if summary_text.startswith("---"):
            parts = summary_text.split("---", 2)
            if len(parts) >= 3:
                # Remove old frontmatter, keep content
                summary_text = parts[2].strip()

        # Generate new frontmatter
        frontmatter = self._generate_frontmatter(
            timestamp=timestamp,
            doc_type="summary",
            title=title,
            transcript_link=transcript_link
        )

        # Create full document
        content = f"{frontmatter}\n{summary_text}"

        # Write to output directory
        filename = self._format_filename(timestamp, "summary")
        output_path = self.output_dir / filename
        output_path.write_text(content)

        print(f"✓ Summary saved: {output_path}")
        return output_path

    def write_meeting(
        self,
        transcript_path: Path,
        summary_path: Optional[Path] = None,
        audio_path: Optional[Path] = None,
        timestamp: Optional[datetime] = None,
        title: Optional[str] = None
    ) -> dict:
        """
        Write complete meeting (transcript + summary) to output directory.

        Args:
            transcript_path: Path to transcript file
            summary_path: Optional path to summary file
            audio_path: Optional path to audio file (will be copied)
            timestamp: Meeting timestamp (default: now)
            title: Optional meeting title

        Returns:
            Dict with paths to created files
        """
        if timestamp is None:
            timestamp = datetime.now()

        result = {}

        # Write transcript
        transcript_file = self.write_transcript(
            transcript_path=transcript_path,
            timestamp=timestamp,
            title=title
        )
        result["transcript"] = transcript_file

        # Write summary if provided
        if summary_path and summary_path.exists():
            summary_file = self.write_summary(
                summary_path=summary_path,
                timestamp=timestamp,
                title=title,
                transcript_link=transcript_file.name
            )
            result["summary"] = summary_file

        # Copy audio if provided and configured to keep
        if audio_path and audio_path.exists():
            audio_filename = self._format_filename(timestamp, "audio").replace(".md", ".wav")
            audio_dest = self.output_dir / audio_filename
            shutil.copy2(audio_path, audio_dest)
            print(f"✓ Audio saved: {audio_dest}")
            result["audio"] = audio_dest

        return result

    def _generate_frontmatter(
        self,
        timestamp: datetime,
        doc_type: str,
        title: Optional[str] = None,
        transcript_link: Optional[str] = None
    ) -> str:
        """Generate YAML frontmatter for markdown files."""
        lines = ["---"]
        lines.append(f'date: {timestamp.strftime("%Y-%m-%d")}')
        lines.append(f'time: {timestamp.strftime("%H:%M")}')
        lines.append(f"type: {doc_type}")

        if title:
            lines.append(f'title: "{title}"')

        if transcript_link:
            lines.append(f"transcript: \"[[{transcript_link}]]\"")

        lines.append(f"tags: [meeting, {doc_type}]")
        lines.append("---")

        return "\n".join(lines)


def main():
    """Test markdown writer."""
    from config import Config

    # Load config
    config = Config()

    # Create writer
    writer = MarkdownWriter(output_dir=config.meetings_dir)

    print(f"Output directory: {writer.output_dir}")
    print(f"Directory exists: {writer.output_dir.exists()}")

    # Find test files
    recordings_dir = Path("./recordings")
    transcripts = sorted(recordings_dir.glob("transcript_*.txt"))
    summaries = sorted(recordings_dir.glob("summary_*.md"))

    if not transcripts:
        print("\nNo test files found. Run test_transcribe.py first.")
        return

    # Use latest files
    latest_transcript = transcripts[-1]
    latest_summary = summaries[-1] if summaries else None

    print(f"\nTest files:")
    print(f"  Transcript: {latest_transcript}")
    print(f"  Summary: {latest_summary}")

    # Write meeting files
    result = writer.write_meeting(
        transcript_path=latest_transcript,
        summary_path=latest_summary,
        title="Test Meeting - Voice Transcription"
    )

    print(f"\n✓ Meeting files written:")
    for key, path in result.items():
        print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
