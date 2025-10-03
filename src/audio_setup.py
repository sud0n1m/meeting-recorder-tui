#!/usr/bin/env python3
"""
PipeWire audio capture setup for meeting recorder.
Creates null sink and loopback devices to capture mic + speaker audio.
"""

import subprocess
import time
from typing import Optional, Dict, List


class AudioCaptureSetup:
    """Manages PipeWire null sink and loopback configuration."""

    def __init__(self):
        self.null_sink_name = "meeting-recorder-sink"
        self.null_sink_id: Optional[str] = None
        self.loopback_ids: List[str] = []
        self.mic_source: Optional[str] = None
        self.speaker_source: Optional[str] = None

    def run_pactl(self, *args) -> str:
        """Run pactl command and return output."""
        cmd = ["pactl"] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def get_default_sources(self) -> Dict[str, str]:
        """Get default microphone and speaker monitor sources."""
        # Get default mic source
        mic = self.run_pactl("get-default-source")

        # Get default sink for speaker monitoring
        default_sink = self.run_pactl("get-default-sink")
        speaker = f"{default_sink}.monitor"

        return {"mic": mic, "speaker": speaker}

    def setup(self) -> bool:
        """
        Setup audio capture pipeline.
        Creates null sink and routes mic + speaker audio to it.
        Returns True on success.
        """
        try:
            print("Setting up audio capture...")

            # Get default sources
            sources = self.get_default_sources()
            self.mic_source = sources["mic"]
            self.speaker_source = sources["speaker"]
            print(f"  Mic source: {self.mic_source}")
            print(f"  Speaker monitor: {self.speaker_source}")

            # Create null sink for mixing
            print(f"  Creating null sink: {self.null_sink_name}")
            output = self.run_pactl(
                "load-module",
                "module-null-sink",
                f"sink_name={self.null_sink_name}",
                f"sink_properties=device.description=Meeting-Recorder-Mix"
            )
            self.null_sink_id = output
            print(f"  Created null sink (ID: {self.null_sink_id})")

            # Create loopback from mic to null sink
            print("  Creating mic loopback...")
            output = self.run_pactl(
                "load-module",
                "module-loopback",
                f"source={self.mic_source}",
                f"sink={self.null_sink_name}",
                "latency_msec=1"
            )
            self.loopback_ids.append(output)
            print(f"  Created mic loopback (ID: {output})")

            # Create loopback from speaker monitor to null sink
            print("  Creating speaker loopback...")
            output = self.run_pactl(
                "load-module",
                "module-loopback",
                f"source={self.speaker_source}",
                f"sink={self.null_sink_name}",
                "latency_msec=1"
            )
            self.loopback_ids.append(output)
            print(f"  Created speaker loopback (ID: {output})")

            # Wait for devices to stabilize
            time.sleep(0.5)

            print("Audio capture setup complete!")
            return True

        except subprocess.CalledProcessError as e:
            print(f"Error setting up audio: {e}")
            self.cleanup()
            return False

    def cleanup(self):
        """Remove all created PipeWire modules."""
        print("Cleaning up audio setup...")

        # Remove loopbacks
        for loopback_id in self.loopback_ids:
            try:
                self.run_pactl("unload-module", loopback_id)
                print(f"  Removed loopback (ID: {loopback_id})")
            except subprocess.CalledProcessError as e:
                print(f"  Warning: Could not remove loopback {loopback_id}: {e}")

        # Remove null sink
        if self.null_sink_id:
            try:
                self.run_pactl("unload-module", self.null_sink_id)
                print(f"  Removed null sink (ID: {self.null_sink_id})")
            except subprocess.CalledProcessError as e:
                print(f"  Warning: Could not remove null sink: {e}")

        print("Cleanup complete")

    def get_monitor_source(self) -> str:
        """Get the monitor source name for the null sink (for recording)."""
        return f"{self.null_sink_name}.monitor"


def main():
    """Test the audio setup."""
    setup = AudioCaptureSetup()

    try:
        if setup.setup():
            print(f"\nRecording source: {setup.get_monitor_source()}")
            print("\nPress Ctrl+C to cleanup and exit...")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        setup.cleanup()


if __name__ == "__main__":
    main()
