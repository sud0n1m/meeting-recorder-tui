#!/usr/bin/env python3
"""
Minimal TUI for meeting recorder with recording timer.
"""

import time
from datetime import timedelta
from typing import Optional
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Static, ProgressBar
from textual.reactive import reactive

from audio_setup import AudioCaptureSetup
from audio_monitor import AudioLevelMonitor


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


class MeetingRecorderApp(App):
    """A minimal TUI for the meeting recorder."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.audio_setup: Optional[AudioCaptureSetup] = None
        self.audio_monitor: Optional[AudioLevelMonitor] = None

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
            yield Static("Press 'q' or Ctrl+C to stop recording", classes="instruction")

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = "Meeting Recorder"
        self.sub_title = "TUI Mode"

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

        # Update UI with audio levels
        self.set_interval(0.1, self.update_levels)

    def update_levels(self) -> None:
        """Update audio level meters with real PipeWire data."""
        if not self.audio_monitor:
            return

        mic_level, speaker_level = self.audio_monitor.get_levels()
        mic_meter = self.query_one("#mic-level", AudioLevelMeter)
        speaker_meter = self.query_one("#speaker-level", AudioLevelMeter)
        mic_meter.level = mic_level
        speaker_meter.level = speaker_level

    def on_unmount(self) -> None:
        """Cleanup when app closes."""
        if self.audio_monitor:
            self.audio_monitor.stop()
        if self.audio_setup:
            self.audio_setup.cleanup()


def run_tui():
    """Run the TUI application."""
    app = MeetingRecorderApp()
    app.run()


if __name__ == "__main__":
    run_tui()
