#!/usr/bin/env python3
"""
Audio level monitoring for PipeWire sources.
Reads actual audio peak levels from PipeWire sources.
"""

import subprocess
import threading
import time
import struct
import numpy as np
from typing import Optional, Callable


class AudioLevelMonitor:
    """Monitors audio levels from PipeWire sources by reading actual audio data."""

    def __init__(self, mic_source: str, speaker_source: str):
        self.mic_source = mic_source
        self.speaker_source = speaker_source
        self.mic_level = 0.0
        self.speaker_level = 0.0
        self.running = False
        self.mic_thread: Optional[threading.Thread] = None
        self.speaker_thread: Optional[threading.Thread] = None
        self.callback: Optional[Callable[[float, float], None]] = None

    def _read_audio_level(self, source_name: str, is_mic: bool):
        """
        Read audio data from a PipeWire source and calculate RMS level.
        Updates the corresponding level attribute.
        """
        process = None
        try:
            # Use parec to record audio from the source
            # Read small chunks (0.1 seconds) for responsive monitoring
            process = subprocess.Popen(
                [
                    "parec",
                    "--device", source_name,
                    "--format", "s16le",  # 16-bit signed PCM little-endian
                    "--rate", "16000",  # Lower sample rate for monitoring
                    "--channels", "1",  # Mono
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            chunk_size = 1600  # 0.1 seconds at 16kHz (16000 samples/sec * 0.1)
            bytes_per_chunk = chunk_size * 2  # 2 bytes per s16 sample

            while self.running:
                try:
                    # Read audio chunk
                    data = process.stdout.read(bytes_per_chunk)
                    if not data:
                        break

                    if len(data) < bytes_per_chunk:
                        continue

                    # Convert bytes to numpy array of int16 samples
                    samples = np.frombuffer(data, dtype=np.int16)

                    # Calculate RMS (Root Mean Square) level
                    rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))

                    # Normalize to 0.0-1.0 range (int16 max is 32768)
                    level = min(rms / 32768.0, 1.0)

                    # Apply some gain/sensitivity adjustment
                    level = min(level * 5.0, 1.0)

                    # Update the appropriate level directly
                    if is_mic:
                        self.mic_level = level
                    else:
                        self.speaker_level = level

                except Exception as e:
                    continue

        except Exception as e:
            pass
        finally:
            if process:
                process.terminate()
                process.wait()

    def _monitor_loop(self):
        """Background loop for callback notifications."""
        while self.running:
            if self.callback:
                self.callback(self.mic_level, self.speaker_level)
            time.sleep(0.05)  # 20 updates per second

    def start(self, callback: Optional[Callable[[float, float], None]] = None):
        """Start monitoring audio levels in background threads."""
        if self.running:
            return

        self.callback = callback
        self.running = True

        # Start separate threads for mic and speaker monitoring
        self.mic_thread = threading.Thread(
            target=self._read_audio_level,
            args=(self.mic_source, True),
            daemon=True
        )
        self.speaker_thread = threading.Thread(
            target=self._read_audio_level,
            args=(self.speaker_source, False),
            daemon=True
        )

        # Start callback thread if callback provided
        if callback:
            self.callback_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True
            )
            self.callback_thread.start()

        self.mic_thread.start()
        self.speaker_thread.start()

    def stop(self):
        """Stop monitoring audio levels."""
        self.running = False
        if self.mic_thread:
            self.mic_thread.join(timeout=1)
            self.mic_thread = None
        if self.speaker_thread:
            self.speaker_thread.join(timeout=1)
            self.speaker_thread = None

    def get_levels(self) -> tuple[float, float]:
        """Get current mic and speaker levels (0.0 to 1.0)."""
        return (self.mic_level, self.speaker_level)


def main():
    """Test the audio monitor."""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.audio_setup import AudioCaptureSetup

    # Setup audio capture first
    setup = AudioCaptureSetup()

    try:
        if not setup.setup():
            print("Failed to setup audio")
            return

        # Create monitor
        monitor = AudioLevelMonitor(setup.mic_source, setup.speaker_source)

        def print_levels(mic, spk):
            mic_bar = "▓" * int(mic * 20)
            spk_bar = "▓" * int(spk * 20)
            print(f"\rMic: {mic_bar:20} {int(mic*100):3}%  |  Spk: {spk_bar:20} {int(spk*100):3}%", end="")

        print("Monitoring audio levels (Press Ctrl+C to stop)...")
        print("Make some noise to test!\n")

        monitor.start(callback=print_levels)

        # Run for 30 seconds or until interrupted
        time.sleep(30)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        if 'monitor' in locals():
            monitor.stop()
        setup.cleanup()


if __name__ == "__main__":
    main()
