#!/usr/bin/env python3
"""
Background processing queue for meeting recordings.
Allows back-to-back meetings without waiting for transcription/summarization.
"""

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from enum import Enum

from transcribe import Transcriber
from summarize import Summarizer
from markdown_writer import MarkdownWriter
from config import Config


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
                    self._notify_status_change(job)

                except Exception as e:
                    # Mark as failed
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
        Process a single recording job.

        Args:
            job: ProcessingJob to process
        """
        # Initialize transcriber
        transcriber = Transcriber(
            model_size=job.whisper_model,
            device=job.whisper_device,
            output_dir=job.audio_file.parent
        )

        # Set the audio file
        transcriber.audio_file = job.audio_file

        # Load Whisper model
        transcriber.load_model()

        # Transcribe
        transcriber.transcribe_audio(job.audio_file)

        # Check if transcription succeeded
        if not transcriber.transcript_file or not transcriber.transcript_file.exists():
            raise Exception("Transcription failed - no transcript file generated")

        # Summarize
        summarizer = Summarizer(
            model=job.ollama_model,
            endpoint=job.ollama_endpoint
        )
        summary_path = summarizer.summarize_file(transcriber.transcript_file)

        # Save to markdown
        markdown_writer = MarkdownWriter(output_dir=job.meetings_dir)
        markdown_writer.write_meeting(
            transcript_path=transcriber.transcript_file,
            summary_path=summary_path,
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
