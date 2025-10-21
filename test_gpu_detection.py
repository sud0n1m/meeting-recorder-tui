#!/usr/bin/env python3
"""Test GPU detection for Whisper transcription."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config
from transcribe import Transcriber

def main():
    """Test GPU detection and model loading."""
    print("="*60)
    print("GPU Detection Test")
    print("="*60)

    # Load config
    config = Config()

    print(f"\nConfiguration:")
    print(f"  Whisper Model: {config.whisper_model}")
    print(f"  Device: {config.whisper_device}")
    print(f"  Compute Type: {config.whisper_compute_type}")

    # Create transcriber
    print(f"\nInitializing transcriber...")
    transcriber = Transcriber(
        model_size=config.whisper_model,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        output_dir=Path("./recordings")
    )

    # Load model (this will trigger device detection)
    print(f"\nLoading model...")
    transcriber.load_model()

    # Show detected device
    print(f"\n{'='*60}")
    print(f"Result: Model loaded successfully!")
    print(f"Device Info: {transcriber.get_device_info()}")
    print(f"{'='*60}")

    # Try to detect PyTorch CUDA availability
    print(f"\nPyTorch CUDA Check:")
    try:
        import torch
        print(f"  PyTorch version: {torch.__version__}")
        print(f"  CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  CUDA device: {torch.cuda.get_device_name(0)}")
            print(f"  CUDA version: {torch.version.cuda}")
    except ImportError:
        print(f"  PyTorch not installed (faster-whisper uses CTranslate2 backend)")

    print(f"\n✓ Test completed successfully!")

if __name__ == "__main__":
    main()
