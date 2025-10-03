#!/usr/bin/env python3
"""Quick test of audio setup."""

import time
from src.audio_setup import AudioCaptureSetup

setup = AudioCaptureSetup()

try:
    if setup.setup():
        print(f"\nSuccess! Recording source: {setup.get_monitor_source()}")
        print("Waiting 5 seconds...")
        time.sleep(5)
except Exception as e:
    print(f"Error: {e}")
finally:
    setup.cleanup()
