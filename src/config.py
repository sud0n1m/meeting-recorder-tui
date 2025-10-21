#!/usr/bin/env python3
"""
Configuration management for meeting recorder.
"""

import yaml
from pathlib import Path
from typing import Dict, Any


class Config:
    """Manage configuration from YAML file."""

    def __init__(self, config_path: Path = None):
        """
        Load configuration from file.

        Args:
            config_path: Path to config.yaml (default: ./config.yaml)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load YAML config file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def get(self, key_path: str, default=None):
        """
        Get config value using dot notation.

        Example:
            config.get("obsidian.vault_path")
            config.get("whisper.model")
        """
        keys = key_path.split(".")
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    @property
    def output_base_path(self) -> Path:
        """Get output base path as Path object."""
        base_path = self.get("output_dir.base_path")
        if not base_path:
            raise ValueError("output_dir.base_path not configured")
        return Path(base_path).expanduser()

    @property
    def meetings_dir(self) -> Path:
        """Get full path to meetings directory."""
        meetings_subdir = self.get("output_dir.meetings_subdir", "meetings")
        return self.output_base_path / meetings_subdir

    @property
    def whisper_model(self) -> str:
        """Get Whisper model name."""
        return self.get("whisper.model", "base")

    @property
    def whisper_device(self) -> str:
        """Get Whisper device."""
        return self.get("whisper.device", "cpu")

    @property
    def whisper_compute_type(self) -> str:
        """Get Whisper compute type."""
        return self.get("whisper.compute_type", "default")

    @property
    def ollama_endpoint(self) -> str:
        """Get Ollama endpoint URL."""
        return self.get("summarization.ollama_endpoint", "http://localhost:11434")

    @property
    def ollama_model(self) -> str:
        """Get Ollama model name."""
        return self.get("summarization.model", "llama3.2:3b")

    @property
    def keep_audio(self) -> bool:
        """Whether to keep audio files."""
        return self.get("output.keep_audio", True)

    @property
    def timestamp_format(self) -> str:
        """Get timestamp format string."""
        return self.get("output.timestamp_format", "%Y-%m-%d_%H-%M-%S")


def main():
    """Test config loading."""
    config = Config()

    print("Configuration loaded successfully!")
    print(f"Output base path: {config.output_base_path}")
    print(f"Meetings dir: {config.meetings_dir}")
    print(f"Whisper model: {config.whisper_model}")
    print(f"Ollama model: {config.ollama_model}")


if __name__ == "__main__":
    main()
