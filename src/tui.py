#!/usr/bin/env python3
"""
Complete TUI for meeting recorder with full workflow integration.
"""

import time
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Static
from textual.reactive import reactive
from textual.worker import Worker, WorkerState

from audio_setup import AudioCaptureSetup
from audio_monitor import AudioLevelMonitor
from transcribe import Transcriber
from summarize import Summarizer
from markdown_writer import MarkdownWriter
from config import Config


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
        self.update(f"🎙️  Recording: {hours:02d}:{minutes:02d}:{seconds:02d}")


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
    """Complete meeting recorder with transcription and summarization."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = Config()
        self.audio_setup: Optional[AudioCaptureSetup] = None
        self.audio_monitor: Optional[AudioLevelMonitor] = None
        self.transcriber: Optional[Transcriber] = None
        self.summarizer: Optional[Summarizer] = None
        self.markdown_writer: Optional[MarkdownWriter] = None
        self.recording_timestamp: Optional[datetime] = None

    CSS = """
    Screen {
        align: center middle;
    }

    #main-container {
        width: 60;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
    }

    RecordingTimer {
        text-align: center;
        width: 100%;
        margin: 1 0;
        text-style: bold;
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

    StatusMessage {
        text-align: center;
        width: 100%;
        margin: 1 0;
        color: $success;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        with Container(id="main-container"):
            yield Static("Meeting Recorder", classes="title")
            yield RecordingTimer()
            with Container(classes="levels-container"):
                yield AudioLevelMeter("Microphone:", id="mic-level")
                yield AudioLevelMeter("Speakers:", id="speaker-level")
            yield StatusMessage(id="status")
            yield Static("Press 'q' or Ctrl+C to stop recording", classes="instruction")

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = "Meeting Recorder"
        self.sub_title = "TUI Mode"
        self.recording_timestamp = datetime.now()

        # Update status
        self.update_status("Initializing audio...")

        # Setup audio capture
        self.audio_setup = AudioCaptureSetup()
        if not self.audio_setup.setup():
            self.exit(message="Failed to setup audio capture")
            return

        # Start audio monitoring
        self.audio_monitor = AudioLevelMonitor(
            self.audio_setup.mic_source,
            self.audio_setup.speaker_source
        )
        self.audio_monitor.start()

        # Initialize transcriber
        self.transcriber = Transcriber(
            model_size=self.config.whisper_model,
            device=self.config.whisper_device,
            output_dir=Path("./recordings")
        )

        # Initialize summarizer
        self.summarizer = Summarizer(
            model=self.config.ollama_model,
            endpoint=self.config.ollama_endpoint
        )

        # Initialize markdown writer
        self.markdown_writer = MarkdownWriter(
            output_dir=self.config.meetings_dir
        )

        # Start recording
        monitor_source = self.audio_setup.get_monitor_source()
        if not self.transcriber.start_recording(monitor_source):
            self.exit(message="Failed to start recording")
            return

        # Update UI with audio levels
        self.set_interval(0.1, self.update_levels)
        self.update_status("🎙️  Recording...")

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
