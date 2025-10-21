#!/usr/bin/env python3
"""
Background processing queue for meeting recordings.
Allows back-to-back meetings without waiting for transcription/summarization.
"""

import queue
import threading
import time
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from enum import Enum

from transcribe import Transcriber
from summarize import Summarizer
from markdown_writer import MarkdownWriter
from config import Config
from server_client import ServerClient, ServerStatus

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('meeting_recorder.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Status of a processing job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingJob:
    """Represents a recording to be processed."""
    job_id: str
    audio_file: Path
    timestamp: datetime
    title: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    ollama_model: str
    ollama_endpoint: str
    meetings_dir: Path
    keep_audio: bool
    status: JobStatus = JobStatus.PENDING
    error_message: Optional[str] = None


class ProcessingQueue:
    """Manages background processing of recordings."""

    def __init__(self, config: Config, max_size: int = 5):
        """
        Initialize processing queue.

        Args:
            config: Application configuration
            max_size: Maximum number of jobs in queue
        """
        self.config = config
        self.queue: queue.Queue = queue.Queue(maxsize=max_size)
        self.jobs: dict[str, ProcessingJob] = {}
        self.worker_thread: Optional[threading.Thread] = None
        self.running: bool = False
        self.lock = threading.Lock()
        self.status_callback: Optional[Callable[[ProcessingJob], None]] = None

    def start(self) -> None:
        """Start the background worker thread."""
        if self.running:
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def stop(self, wait: bool = True) -> None:
        """
        Stop the background worker thread.

        Args:
            wait: If True, wait for current job to finish
        """
        self.running = False
        if wait and self.worker_thread:
            self.worker_thread.join(timeout=10)

    def enqueue(self, audio_file: Path, timestamp: datetime, title: str) -> str:
        """
        Add a recording to the processing queue.

        Args:
            audio_file: Path to recorded audio file
            timestamp: Recording timestamp
            title: Meeting title

        Returns:
            Job ID

        Raises:
            queue.Full: If queue is at max capacity
        """
        job_id = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{title}"

        job = ProcessingJob(
            job_id=job_id,
            audio_file=audio_file,
            timestamp=timestamp,
            title=title,
            whisper_model=self.config.whisper_model,
            whisper_device=self.config.whisper_device,
            whisper_compute_type=self.config.whisper_compute_type,
            ollama_model=self.config.ollama_model,
            ollama_endpoint=self.config.ollama_endpoint,
            meetings_dir=self.config.meetings_dir,
            keep_audio=self.config.keep_audio,
            status=JobStatus.PENDING
        )

        with self.lock:
            self.jobs[job_id] = job

        try:
            self.queue.put(job, block=False)
            return job_id
        except queue.Full:
            with self.lock:
                del self.jobs[job_id]
            raise

    def get_status(self) -> dict:
        """
        Get current queue status.

        Returns:
            Dictionary with queue statistics
        """
        with self.lock:
            return {
                "pending": sum(1 for j in self.jobs.values() if j.status == JobStatus.PENDING),
                "processing": sum(1 for j in self.jobs.values() if j.status == JobStatus.PROCESSING),
                "completed": sum(1 for j in self.jobs.values() if j.status == JobStatus.COMPLETED),
                "failed": sum(1 for j in self.jobs.values() if j.status == JobStatus.FAILED),
                "total": len(self.jobs)
            }

    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        """Get a specific job by ID."""
        with self.lock:
            return self.jobs.get(job_id)

    def set_status_callback(self, callback: Callable[[ProcessingJob], None]) -> None:
        """Set callback function to be called when job status changes."""
        self.status_callback = callback

    def _worker(self) -> None:
        """Background worker that processes jobs from the queue."""
        while self.running:
            try:
                # Get next job with timeout
                job = self.queue.get(timeout=1)

                logger.info(f"Starting job: {job.job_id}")
                logger.info(f"  Title: {job.title}")
                logger.info(f"  Audio: {job.audio_file}")

                # Update status
                with self.lock:
                    job.status = JobStatus.PROCESSING
                self._notify_status_change(job)

                # Process the job
                try:
                    self._process_job(job)

                    # Mark as completed
                    with self.lock:
                        job.status = JobStatus.COMPLETED
                    logger.info(f"✓ Job completed successfully: {job.job_id}")
                    self._notify_status_change(job)

                except Exception as e:
                    # Mark as failed
                    logger.error(f"✗ Job failed: {job.job_id}")
                    logger.error(f"  Error: {str(e)}", exc_info=True)
                    with self.lock:
                        job.status = JobStatus.FAILED
                        job.error_message = str(e)
                    self._notify_status_change(job)

                finally:
                    self.queue.task_done()

            except queue.Empty:
                # No jobs in queue, continue waiting
                continue
            except Exception as e:
                # Unexpected error in worker
                print(f"Worker error: {e}")
                time.sleep(1)

    def _process_job(self, job: ProcessingJob) -> None:
        """
        Process a single recording job with server-first, local fallback strategy.

        Args:
            job: ProcessingJob to process
        """
        processing_mode = self.config.processing_mode
        used_server = False

        # Try server processing first (if hybrid or remote mode)
        if processing_mode in ["hybrid", "remote"] and self.config.server_enabled:
            try:
                print(f"\n{'='*60}")
                print(f"Trying remote server processing...")
                print(f"{'='*60}")

                server_result = self._try_server_processing(job)

                if server_result:
                    print(f"✓ Server processing successful!")
                    used_server = True
                    return  # Success! Job completed on server

                elif processing_mode == "remote":
                    # Remote-only mode: fail if server doesn't work
                    raise Exception("Server processing failed and mode is 'remote' (no local fallback)")

                else:
                    # Hybrid mode: fall back to local
                    print(f"⚠️  Server processing failed, falling back to local processing...")

            except Exception as e:
                if processing_mode == "remote":
                    raise  # Re-raise in remote-only mode
                print(f"⚠️  Server error: {e}")
                print(f"Falling back to local processing...")

        # Local processing (either mode=local, or fallback from hybrid)
        if not used_server:
            print(f"\n{'='*60}")
            print(f"Processing locally...")
            print(f"{'='*60}")
            self._process_locally(job)

    def _try_server_processing(self, job: ProcessingJob) -> bool:
        """
        Try to process job on remote server.

        Args:
            job: ProcessingJob to process

        Returns:
            True if successful, False otherwise
        """
        # Create server client
        client = ServerClient(
            server_url=self.config.server_url,
            api_key=self.config.server_api_key,
            timeout=self.config.server_timeout,
            health_check_timeout=self.config.server_health_check_timeout
        )

        try:
            # Check server health
            print("Checking server availability...")
            status = client.check_health()

            if status != ServerStatus.AVAILABLE:
                print(f"Server not available: {status.value}")
                return False

            print("Server is available, uploading audio...")

            # Process on server
            result = client.process_recording(
                audio_file=job.audio_file,
                title=job.title,
                whisper_model=job.whisper_model,
                ollama_model=job.ollama_model
            )

            if not result.success:
                print(f"Server processing failed: {result.error_message}")
                return False

            print(f"Server processing completed in {result.processing_time:.1f}s")

            # Save results locally
            self._save_server_results(job, result.transcript_text, result.summary_text)

            return True

        finally:
            client.close()

    def _process_locally(self, job: ProcessingJob) -> None:
        """
        Process job locally (original implementation).

        Args:
            job: ProcessingJob to process
        """
        logger.info("Starting local processing")
        logger.info(f"  Model: {job.whisper_model}")
        logger.info(f"  Device: {job.whisper_device}")
        logger.info(f"  Compute type: {job.whisper_compute_type}")

        # Initialize transcriber
        logger.info("Initializing transcriber...")
        transcriber = Transcriber(
            model_size=job.whisper_model,
            device=job.whisper_device,
            compute_type=job.whisper_compute_type,
            output_dir=job.audio_file.parent
        )

        # Set the audio file
        transcriber.audio_file = job.audio_file
        logger.info(f"Audio file: {job.audio_file}")
        logger.info(f"Audio size: {job.audio_file.stat().st_size / 1024 / 1024:.1f} MB")

        # Load Whisper model
        logger.info("Loading Whisper model...")
        transcriber.load_model()
        logger.info(f"Model loaded on: {transcriber.get_device_info()}")

        # Transcribe
        logger.info("Starting transcription...")
        transcriber.transcribe_audio(job.audio_file)
        logger.info("Transcription completed")

        # Check if transcription succeeded
        if not transcriber.transcript_file or not transcriber.transcript_file.exists():
            logger.error(f"Transcript file not found: {transcriber.transcript_file}")
            raise Exception("Transcription failed - no transcript file generated")

        logger.info(f"Transcript file: {transcriber.transcript_file}")
        transcript_size = transcriber.transcript_file.stat().st_size
        logger.info(f"Transcript size: {transcript_size} bytes")

        if transcript_size < 100:
            logger.warning(f"Transcript file is very small ({transcript_size} bytes), may be empty")

        # Summarize
        logger.info("Starting summarization...")
        logger.info(f"  LLM: {job.ollama_model}")
        logger.info(f"  Endpoint: {job.ollama_endpoint}")
        summarizer = Summarizer(
            model=job.ollama_model,
            endpoint=job.ollama_endpoint
        )
        summary_path = summarizer.summarize_file(transcriber.transcript_file)
        logger.info(f"Summary file: {summary_path}")

        # Save to markdown
        logger.info("Writing markdown file...")
        logger.info(f"  Output dir: {job.meetings_dir}")
        markdown_writer = MarkdownWriter(output_dir=job.meetings_dir)
        markdown_writer.write_meeting(
            transcript_path=transcriber.transcript_file,
            summary_path=summary_path,
            audio_path=job.audio_file if job.keep_audio else None,
            timestamp=job.timestamp,
            title=job.title
        )
        logger.info("Markdown file written successfully")

    def _save_server_results(self, job: ProcessingJob, transcript: str, summary: str) -> None:
        """
        Save results from server processing to local files.

        Args:
            job: ProcessingJob being processed
            transcript: Transcript text from server
            summary: Summary text from server
        """
        # Create transcript file
        transcript_file = job.audio_file.parent / f"transcript_{job.timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        transcript_file.write_text(transcript)

        # Create summary file
        summary_file = job.audio_file.parent / f"summary_{job.timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        summary_file.write_text(summary)

        # Save to markdown
        markdown_writer = MarkdownWriter(output_dir=job.meetings_dir)
        markdown_writer.write_meeting(
            transcript_path=transcript_file,
            summary_path=summary_file,
            audio_path=job.audio_file if job.keep_audio else None,
            timestamp=job.timestamp,
            title=job.title
        )

    def _notify_status_change(self, job: ProcessingJob) -> None:
        """Notify callback of status change."""
        if self.status_callback:
            try:
                self.status_callback(job)
            except Exception as e:
                print(f"Status callback error: {e}")
