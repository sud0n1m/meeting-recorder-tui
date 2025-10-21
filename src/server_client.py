#!/usr/bin/env python3
"""
Server API client for remote processing.
Handles communication with remote processing server for transcription and summarization.
"""

import requests
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class ServerStatus(Enum):
    """Server availability status."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass
class ProcessingResult:
    """Result from server processing."""
    success: bool
    transcript_text: Optional[str] = None
    summary_text: Optional[str] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None


class ServerClient:
    """Client for remote processing server."""

    def __init__(
        self,
        server_url: str,
        api_key: str = "",
        timeout: int = 300,
        health_check_timeout: int = 5
    ):
        """
        Initialize server client.

        Args:
            server_url: Base URL of processing server
            api_key: Optional API key for authentication
            timeout: Timeout for processing requests (seconds)
            health_check_timeout: Timeout for health checks (seconds)
        """
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.health_check_timeout = health_check_timeout
        self.session = requests.Session()

        # Set up headers
        self.headers = {
            "User-Agent": "MeetingRecorder/0.4"
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def check_health(self) -> ServerStatus:
        """
        Check if server is available.

        Returns:
            ServerStatus indicating availability
        """
        try:
            response = self.session.get(
                f"{self.server_url}/health",
                headers=self.headers,
                timeout=self.health_check_timeout
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    return ServerStatus.AVAILABLE

            return ServerStatus.ERROR

        except requests.exceptions.Timeout:
            return ServerStatus.UNAVAILABLE
        except requests.exceptions.ConnectionError:
            return ServerStatus.UNAVAILABLE
        except Exception as e:
            print(f"Health check error: {e}")
            return ServerStatus.ERROR

    def process_recording(
        self,
        audio_file: Path,
        title: str,
        whisper_model: str = "base",
        ollama_model: str = "qwen3:8b-q8_0"
    ) -> ProcessingResult:
        """
        Upload audio and process on server.

        Args:
            audio_file: Path to audio file
            title: Meeting title
            whisper_model: Whisper model to use
            ollama_model: LLM model for summarization

        Returns:
            ProcessingResult with transcript and summary
        """
        start_time = time.time()

        try:
            # Step 1: Upload audio file
            print(f"Uploading {audio_file.name} to server...")
            with open(audio_file, "rb") as f:
                files = {"audio": (audio_file.name, f, "audio/wav")}
                data = {
                    "title": title,
                    "whisper_model": whisper_model,
                    "ollama_model": ollama_model
                }

                response = self.session.post(
                    f"{self.server_url}/api/process",
                    headers=self.headers,
                    files=files,
                    data=data,
                    timeout=self.timeout
                )

            if response.status_code != 200:
                return ProcessingResult(
                    success=False,
                    error_message=f"Server returned {response.status_code}: {response.text}"
                )

            result_data = response.json()

            if not result_data.get("success"):
                return ProcessingResult(
                    success=False,
                    error_message=result_data.get("error", "Unknown server error")
                )

            processing_time = time.time() - start_time

            return ProcessingResult(
                success=True,
                transcript_text=result_data.get("transcript"),
                summary_text=result_data.get("summary"),
                processing_time=processing_time
            )

        except requests.exceptions.Timeout:
            return ProcessingResult(
                success=False,
                error_message=f"Server timeout after {self.timeout} seconds"
            )
        except requests.exceptions.ConnectionError:
            return ProcessingResult(
                success=False,
                error_message="Failed to connect to server"
            )
        except Exception as e:
            return ProcessingResult(
                success=False,
                error_message=f"Processing error: {str(e)}"
            )

    def close(self):
        """Close the session."""
        self.session.close()


def main():
    """Test server client."""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python server_client.py <server_url> <audio_file>")
        sys.exit(1)

    server_url = sys.argv[1]
    audio_file = Path(sys.argv[2])

    if not audio_file.exists():
        print(f"Error: Audio file not found: {audio_file}")
        sys.exit(1)

    client = ServerClient(server_url)

    print("="*60)
    print("Server Client Test")
    print("="*60)

    # Check health
    print(f"\nChecking server health...")
    status = client.check_health()
    print(f"Status: {status.value}")

    if status != ServerStatus.AVAILABLE:
        print("❌ Server is not available")
        sys.exit(1)

    # Process recording
    print(f"\nProcessing {audio_file.name}...")
    result = client.process_recording(
        audio_file=audio_file,
        title="Test Meeting"
    )

    print("\n" + "="*60)
    if result.success:
        print("✓ Processing successful!")
        print(f"Processing time: {result.processing_time:.1f}s")
        print(f"\nTranscript length: {len(result.transcript_text)} chars")
        print(f"Summary length: {len(result.summary_text)} chars")
    else:
        print("❌ Processing failed")
        print(f"Error: {result.error_message}")
    print("="*60)

    client.close()


if __name__ == "__main__":
    main()
