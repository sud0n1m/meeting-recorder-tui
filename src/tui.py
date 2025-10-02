#!/usr/bin/env python3
"""
Minimal TUI for meeting recorder with recording timer.
"""

import time
from datetime import timedelta
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Static
from textual.reactive import reactive


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


class MeetingRecorderApp(App):
    """A minimal TUI for the meeting recorder."""

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
            yield Static("Press 'q' or Ctrl+C to stop recording", classes="instruction")

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = "Meeting Recorder"
        self.sub_title = "TUI Mode"


def run_tui():
    """Run the TUI application."""
    app = MeetingRecorderApp()
    app.run()


if __name__ == "__main__":
    run_tui()
