#!/usr/bin/env python3
"""
Complete TUI for meeting recorder with full workflow integration.
Version 0.2: Multi-screen workflow with improved UX.
"""

import time
import re
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static, Input, Footer, Label
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
    READY = "ready"  # Pre-recording dashboard
    RECORDING = "recording"  # Recording in progress
    PROCESSING = "processing"  # Post-recording processing
    DONE = "done"  # Completed


class MeetingTitleInput(Input):
    """Editable meeting title input field."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            value="Untitled",
            placeholder="Meeting title...",
            *args,
            **kwargs
        )


class RecordingTimer(Static):
    """Widget to display recording timer."""

    elapsed_seconds = reactive(0)

    def on_mount(self) -> None:
        """Start the timer when widget is mounted."""
        self.start_time = time.time()
        self.update_timer = self.set_interval(1, self.tick)

    def tick(self) -> None:
        """Update the elapsed time."""
        self.elapsed_seconds = int(time.time() - self.start_time)

    def watch_elapsed_seconds(self, elapsed: int) -> None:
        """Update the display when elapsed time changes."""
        td = timedelta(seconds=elapsed)
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        seconds = td.seconds % 60
        self.update(f"🔴 RECORDING: {hours:02d}:{minutes:02d}:{seconds:02d}")


class AudioLevelMeter(Static):
    """Widget to display audio level with label and bar."""

    level = reactive(0.0)

    def __init__(self, label: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.label = label

    def watch_level(self, level: float) -> None:
        """Update the display when level changes."""
        # Create visual bar with blocks
        bar_width = 20
        filled = int(level * bar_width)
        bar = "▓" * filled + "░" * (bar_width - filled)
        percentage = int(level * 100)
        self.update(f"{self.label:12} {bar}  [{percentage:3d}%]")


class StatusMessage(Static):
    """Widget to display current status message."""

    status = reactive("")

    def watch_status(self, status: str) -> None:
        """Update status display."""
        self.update(status)


class MeetingRecorderApp(App):
    """Complete meeting recorder with transcription and summarization. Version 0.2."""

    CSS = """
    Screen {
        align: center middle;
    }

    #main-container {
        width: 70;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
    }

    .title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    RecordingTimer {
        text-align: center;
        width: 100%;
        margin: 1 0;
        text-style: bold;
        color: $error;
    }

    AudioLevelMeter {
        width: 100%;
        margin: 0 0;
    }

    .levels-container {
        margin: 1 0;
    }

    .instruction {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    .config-box, .recent-box, .action-box {
        border: solid $primary;
        padding: 1;
        margin: 1 0;
    }

    .section-title {
        text-style: bold;
        margin-bottom: 1;
    }

    MeetingTitleInput {
        margin: 1 0;
        width: 100%;
    }

    StatusMessage {
        text-align: center;
        width: 100%;
        margin: 1 0;
        color: $success;
    }

    Footer {
        background: $boost;
    }
    """

    BINDINGS = [
        Binding("r", "start_recording", "Start Recording", show=False, priority=True),
        Binding("enter", "context_enter", "Enter", show=False, priority=True),
        Binding("s", "stop_and_save", "Stop & Save", show=False, priority=True),
        Binding("c", "cancel_recording", "Cancel", show=False, priority=True),
        Binding("escape", "context_escape", "Escape", show=False, priority=True),
        Binding("t", "edit_title", "Edit Title", show=False, priority=True),
        Binding("q", "quit_app", "Quit", show=False, priority=True),
        Binding("question_mark", "show_help", "Help", show=False),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = Config()
        self.state = AppState.READY
        self.audio_setup: Optional[AudioCaptureSetup] = None
        self.audio_monitor: Optional[AudioLevelMonitor] = None
        self.transcriber: Optional[Transcriber] = None
        self.summarizer: Optional[Summarizer] = None
        self.markdown_writer: Optional[MarkdownWriter] = None
        self.recording_timestamp: Optional[datetime] = None
        self.meeting_title: str = "Untitled"
        self.title_editing: bool = False

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        with Container(id="main-container"):
            yield Static("", id="screen-content")
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = "Meeting Recorder"
        self.sub_title = "v0.2"

        # Initialize services
        self.summarizer = Summarizer(
            model=self.config.ollama_model,
            endpoint=self.config.ollama_endpoint
        )
        self.markdown_writer = MarkdownWriter(
            output_dir=self.config.meetings_dir
        )

        # Show dashboard
        self.render_dashboard()

    def render_dashboard(self) -> None:
        """Render the pre-recording dashboard screen."""
        self.state = AppState.READY
        content = self.query_one("#screen-content", Static)

        # Build dashboard content
        dashboard_text = """🎙️  Ready to Record

Configuration:
  • Whisper Model: {whisper_model} ({device})
  • Output: {output_dir}
  • LLM: {llm_model}

Recent Recordings:
{recent}

Press [R] or [Enter] to Start Recording
Press [Q] to Quit
        """.format(
            whisper_model=self.config.whisper_model,
            device=self.config.whisper_device,
            output_dir=str(self.config.meetings_dir),
            llm_model=self.config.ollama_model,
            recent=self._get_recent_recordings()
        )

        content.update(dashboard_text)

    def _get_recent_recordings(self) -> str:
        """Get list of 3 most recent recordings."""
        try:
            meetings_dir = self.config.meetings_dir
            if not meetings_dir.exists():
                return "  (No recordings yet)"

            # Find markdown files
            md_files = sorted(meetings_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]

            if not md_files:
                return "  (No recordings yet)"

            recent_list = []
            for f in md_files:
                # Parse filename: YYYY-MM-DD_HH-MM-SS_Title.md
                name = f.stem
                parts = name.split("_", 2)
                if len(parts) >= 2:
                    date_part = parts[0]
                    time_part = parts[1].replace("-", ":")
                    title_part = parts[2] if len(parts) > 2 else "Untitled"
                    recent_list.append(f"  • {date_part} {time_part} - {title_part}")

            return "\n".join(recent_list) if recent_list else "  (No recordings yet)"
        except Exception:
            return "  (Unable to load recent recordings)"

    def render_recording_screen(self) -> None:
        """Render the recording screen."""
        self.state = AppState.RECORDING
        content = self.query_one("#screen-content", Static)

        # Create recording screen layout (will be updated dynamically)
        recording_text = """🔴 RECORDING: 00:00:00

Meeting Title: {title}
Started: {start_time}

Audio Levels:
  Microphone:    ░░░░░░░░░░░░░░░░░░░░  [  0%]
  Speakers:      ░░░░░░░░░░░░░░░░░░░░  [  0%]

Status: Recording...

[S] Stop & Save  |  [C] Cancel  |  [T] Edit Title
        """.format(
            title=self.meeting_title,
            start_time=self.recording_timestamp.strftime("%Y-%m-%d %H:%M") if self.recording_timestamp else ""
        )

        content.update(recording_text)

    def update_levels(self) -> None:
        """Update audio level meters with real PipeWire data."""
        if not self.audio_monitor:
            return

        mic_level, speaker_level = self.audio_monitor.get_levels()
        mic_meter = self.query_one("#mic-level", AudioLevelMeter)
        speaker_meter = self.query_one("#speaker-level", AudioLevelMeter)
        mic_meter.level = mic_level
        speaker_meter.level = speaker_level

    def update_status(self, message: str) -> None:
        """Update status message."""
        try:
            status_widget = self.query_one("#status", StatusMessage)
            status_widget.status = message
        except:
            pass  # Widget not yet mounted

    def action_quit(self) -> None:
        """Handle quit action - process recording before exiting."""
        # Start processing in background worker
        self.run_worker(self.process_recording, exclusive=True, thread=True)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.state == WorkerState.SUCCESS:
            # Processing complete, exit
            time.sleep(2)  # Show final status for 2 seconds
            self.exit()
        elif event.state == WorkerState.ERROR:
            self.update_status(f"❌ Error during processing")
            time.sleep(2)
            self.exit()

    def on_unmount(self) -> None:
        """Cleanup when app closes."""
        if self.audio_monitor:
            self.audio_monitor.stop()
        if self.audio_setup:
            self.audio_setup.cleanup()

    def process_recording(self) -> None:
        """Process the recording: transcribe, summarize, and save."""
        try:
            # Stop recording
            self.update_status("⏹️  Stopping recording...")
            if self.transcriber:
                self.transcriber.stop_recording()
                time.sleep(1)  # Wait for file to be written

            # Load Whisper model if not already loaded
            if not self.transcriber.model:
                self.update_status("📥 Loading transcription model...")
                self.transcriber.load_model()

            # Transcribe
            if self.transcriber.audio_file and self.transcriber.audio_file.exists():
                self.update_status("📝 Transcribing audio...")
                self.transcriber.transcribe_audio(self.transcriber.audio_file)

                # Summarize
                if self.transcriber.transcript_file and self.transcriber.transcript_file.exists():
                    self.update_status("🤖 Generating summary...")
                    summary_path = self.summarizer.summarize_file(
                        self.transcriber.transcript_file
                    )

                    # Save to markdown
                    self.update_status("💾 Saving to vault...")
                    result = self.markdown_writer.write_meeting(
                        transcript_path=self.transcriber.transcript_file,
                        summary_path=summary_path,
                        audio_path=self.transcriber.audio_file if self.config.keep_audio else None,
                        timestamp=self.recording_timestamp,
                        title=f"Meeting {self.recording_timestamp.strftime('%Y-%m-%d %H:%M')}"
                    )

                    self.update_status(f"✅ Saved! ({len(result)} files)")
                else:
                    self.update_status("⚠️  No transcript generated")
            else:
                self.update_status("⚠️  No audio recorded")

        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}")


def run_tui():
    """Run the TUI application."""
    app = MeetingRecorderApp()
    app.run()


if __name__ == "__main__":
    run_tui()
