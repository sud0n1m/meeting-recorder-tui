#!/usr/bin/env python3
"""
Meeting Recorder TUI - Version 0.2 (Simplified)
Multi-screen workflow with improved UX.
"""

import time
import re
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Input, Footer, Header
from textual.reactive import reactive
from textual.worker import Worker, WorkerState
from textual.binding import Binding

from audio_setup import AudioCaptureSetup
from audio_monitor import AudioLevelMonitor
from transcribe import Transcriber
from summarize import Summarizer
from markdown_writer import MarkdownWriter
from config import Config


class AppState(Enum):
    """Application state machine."""
    READY = "ready"
    RECORDING = "recording"
    PROCESSING = "processing"


class MeetingRecorderApp(App):
    """Meeting recorder with 3-screen workflow."""

    CSS = """
    Screen {
        align: center middle;
    }

    #content {
        width: 70;
        height: auto;
        border: heavy $accent;
        padding: 2;
    }

    .center {
        text-align: center;
    }

    .bold {
        text-style: bold;
    }

    .muted {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("r", "start_recording", "[R]ecord", key_display="r"),
        Binding("enter", "context_enter", "Enter", show=False),
        Binding("s", "stop_and_save", "[S]top&Save", key_display="s"),
        Binding("c", "cancel_recording", "[C]ancel", key_display="c"),
        Binding("t", "edit_title", "[T]itle", key_display="t"),
        Binding("escape", "cancel_title_edit", "Esc", show=False),
        Binding("q", "quit_app", "[Q]uit", key_display="q"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = Config()
        self.state = AppState.READY
        self.meeting_title = "Untitled"
        self.recording_timestamp: Optional[datetime] = None
        self.audio_setup: Optional[AudioCaptureSetup] = None
        self.audio_monitor: Optional[AudioLevelMonitor] = None
        self.transcriber: Optional[Transcriber] = None
        self.title_input: Optional[Input] = None
        self.is_editing_title: bool = False

    def compose(self) -> ComposeResult:
        """Create UI."""
        yield Header()
        with Container(id="content"):
            yield Static("", id="main-content")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize app."""
        self.title = "Meeting Recorder v0.2"
        self.show_dashboard()

    def show_dashboard(self) -> None:
        """Show pre-recording dashboard."""
        self.state = AppState.READY
        content = self.query_one("#main-content", Static)

        dashboard = f"""🎙️  Ready to Record

Configuration:
  • Whisper: {self.config.whisper_model} ({self.config.whisper_device})
  • Output: {self.config.meetings_dir}
  • LLM: {self.config.ollama_model}

Press [R] or [Enter] to Start Recording
Press [Q] to Quit"""

        content.update(dashboard)

    def action_start_recording(self) -> None:
        """Start recording."""
        if self.state != AppState.READY:
            return

        self.recording_timestamp = datetime.now()
        self.state = AppState.RECORDING

        # Initialize audio
        content = self.query_one("#main-content", Static)
        content.update("🔄 Initializing audio...")

        try:
            # Setup audio capture
            self.audio_setup = AudioCaptureSetup()
            if not self.audio_setup.setup():
                content.update("❌ Failed to setup audio")
                time.sleep(2)
                self.show_dashboard()
                return

            # Initialize transcriber
            self.transcriber = Transcriber(
                model_size=self.config.whisper_model,
                device=self.config.whisper_device,
                output_dir=Path("./recordings")
            )

            # Start recording
            monitor_source = self.audio_setup.get_monitor_source()
            if not self.transcriber.start_recording(monitor_source):
                content.update("❌ Failed to start recording")
                time.sleep(2)
                self.show_dashboard()
                return

            # Start audio monitoring
            self.audio_monitor = AudioLevelMonitor(
                self.audio_setup.mic_source,
                self.audio_setup.speaker_source
            )
            self.audio_monitor.start()

            # Show recording screen
            self.show_recording_screen()
            self.set_interval(1, self.update_recording_display)

        except Exception as e:
            content.update(f"❌ Error: {str(e)}")
            time.sleep(2)
            self.show_dashboard()

    def show_recording_screen(self) -> None:
        """Show recording screen."""
        content = self.query_one("#main-content", Static)
        elapsed = self._get_elapsed_time()

        # Get audio levels
        mic_level = 0.0
        speaker_level = 0.0
        if self.audio_monitor:
            mic_level, speaker_level = self.audio_monitor.get_levels()

        # Create audio level bars
        mic_bar = self._create_level_bar(mic_level)
        speaker_bar = self._create_level_bar(speaker_level)

        title_display = f"Meeting: {self.meeting_title}"
        if self.is_editing_title:
            title_display = f"Meeting: > {self.meeting_title}_ (editing - press Enter to save)"

        recording_display = f"""🔴 RECORDING: {elapsed}

{title_display}
Started: {self.recording_timestamp.strftime("%Y-%m-%d %H:%M") if self.recording_timestamp else ""}

Audio Levels:
  Microphone:  {mic_bar}  [{int(mic_level * 100):3d}%]
  Speakers:    {speaker_bar}  [{int(speaker_level * 100):3d}%]

Press [S] to Stop & Save  |  [C] to Cancel  |  [T] to Edit Title"""

        content.update(recording_display)

    def _create_level_bar(self, level: float) -> str:
        """Create a visual level bar."""
        bar_width = 20
        filled = int(level * bar_width)
        return "▓" * filled + "░" * (bar_width - filled)

    def _get_elapsed_time(self) -> str:
        """Get formatted elapsed time."""
        if not self.recording_timestamp:
            return "00:00:00"

        elapsed = int((datetime.now() - self.recording_timestamp).total_seconds())
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def update_recording_display(self) -> None:
        """Update recording display with current time."""
        if self.state == AppState.RECORDING:
            self.show_recording_screen()

    def action_stop_and_save(self) -> None:
        """Stop recording and save."""
        if self.state != AppState.RECORDING:
            return

        self.state = AppState.PROCESSING
        content = self.query_one("#main-content", Static)
        content.update("⏹️  Stopping recording...\nPlease wait...")

        # Stop the update interval
        for timer in self._timers:
            timer.stop()

        # Process in background
        self.run_worker(self.process_recording, exclusive=True, thread=True)

    def action_cancel_recording(self) -> None:
        """Cancel recording without saving."""
        if self.state != AppState.RECORDING:
            return

        content = self.query_one("#main-content", Static)
        content.update("❌ Cancelling recording...")

        # Stop recording
        if self.transcriber:
            self.transcriber.stop_recording()

        # Cleanup audio
        if self.audio_monitor:
            self.audio_monitor.stop()
        if self.audio_setup:
            self.audio_setup.cleanup()

        # Delete audio file if exists
        if self.transcriber and self.transcriber.audio_file and self.transcriber.audio_file.exists():
            try:
                self.transcriber.audio_file.unlink()
            except:
                pass

        time.sleep(1)
        self.show_dashboard()

    def process_recording(self) -> None:
        """Process the recording: transcribe, summarize, save."""
        content = self.query_one("#main-content", Static)

        try:
            # Stop recording
            content.update("⏹️  Stopping recording...")
            if self.transcriber:
                self.transcriber.stop_recording()
                time.sleep(1)

            # Cleanup audio
            if self.audio_monitor:
                self.audio_monitor.stop()
            if self.audio_setup:
                self.audio_setup.cleanup()

            # Load Whisper model
            content.update("📥 Loading transcription model...")
            if not self.transcriber.model:
                self.transcriber.load_model()

            # Transcribe
            if self.transcriber.audio_file and self.transcriber.audio_file.exists():
                content.update("📝 Transcribing audio...\nThis may take a few minutes...")
                self.transcriber.transcribe_audio(self.transcriber.audio_file)

                # Summarize
                if self.transcriber.transcript_file and self.transcriber.transcript_file.exists():
                    content.update("🤖 Generating summary...")

                    # Initialize summarizer
                    summarizer = Summarizer(
                        model=self.config.ollama_model,
                        endpoint=self.config.ollama_endpoint
                    )
                    markdown_writer = MarkdownWriter(
                        output_dir=self.config.meetings_dir
                    )

                    summary_path = summarizer.summarize_file(
                        self.transcriber.transcript_file
                    )

                    # Save to markdown with sanitized title
                    content.update("💾 Saving to vault...")
                    sanitized_title = self._sanitize_title(self.meeting_title)
                    result = markdown_writer.write_meeting(
                        transcript_path=self.transcriber.transcript_file,
                        summary_path=summary_path,
                        audio_path=self.transcriber.audio_file if self.config.keep_audio else None,
                        timestamp=self.recording_timestamp,
                        title=sanitized_title
                    )

                    content.update(f"✅ Saved! ({len(result)} files)\n\nPress [Q] to quit or [R] to record again")
                    self.state = AppState.READY
                else:
                    content.update("⚠️  No transcript generated")
                    time.sleep(2)
                    self.show_dashboard()
            else:
                content.update("⚠️  No audio recorded")
                time.sleep(2)
                self.show_dashboard()

        except Exception as e:
            content.update(f"❌ Error: {str(e)}\n\nPress [Q] to quit or [R] to try again")
            self.state = AppState.READY

    def _sanitize_title(self, title: str) -> str:
        """Sanitize title for filename."""
        # Replace spaces with hyphens
        title = title.replace(" ", "-")
        # Remove special characters except hyphens and underscores
        title = re.sub(r'[^a-zA-Z0-9\-_]', '', title)
        return title or "Untitled"

    def action_context_enter(self) -> None:
        """Context-aware Enter key."""
        if self.state == AppState.READY:
            # Start recording from dashboard
            self.action_start_recording()
        elif self.state == AppState.RECORDING and self.is_editing_title:
            # Save title when editing
            self.is_editing_title = False
            self.show_recording_screen()

    def action_edit_title(self) -> None:
        """Start editing the meeting title."""
        if self.state != AppState.RECORDING or self.is_editing_title:
            return

        self.is_editing_title = True
        self.show_recording_screen()

        # Create a simple input mechanism using the bell pattern
        # User can type and we'll capture it
        def handle_key(event):
            if self.is_editing_title:
                if hasattr(event, 'character') and event.character:
                    if event.character.isprintable():
                        self.meeting_title += event.character
                        self.show_recording_screen()
                elif hasattr(event, 'key'):
                    if event.key == 'backspace':
                        self.meeting_title = self.meeting_title[:-1] if self.meeting_title else ""
                        self.show_recording_screen()

    def action_cancel_title_edit(self) -> None:
        """Cancel title editing."""
        if self.is_editing_title:
            self.is_editing_title = False
            self.show_recording_screen()

    def on_key(self, event) -> None:
        """Handle key presses for title editing."""
        if self.is_editing_title and self.state == AppState.RECORDING:
            if event.character and event.character.isprintable():
                self.meeting_title += event.character
                self.show_recording_screen()
                event.prevent_default()
            elif event.key == "backspace":
                self.meeting_title = self.meeting_title[:-1] if self.meeting_title else ""
                self.show_recording_screen()
                event.prevent_default()

    def action_quit_app(self) -> None:
        """Quit application."""
        if self.state == AppState.RECORDING:
            # Cancel recording first
            self.action_cancel_recording()
        self.exit()


def run_tui():
    """Run the TUI application."""
    app = MeetingRecorderApp()
    app.run()


if __name__ == "__main__":
    run_tui()
