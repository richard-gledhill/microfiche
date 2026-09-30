"""Reverses a filing job by replaying its recorded moves in reverse."""
# Todo: Not wired into rollback yet.

from __future__ import annotations

import json
from pathlib import Path

from core.models.audit_event import AuditEvent
from core.models.job import Job
from core.utils.filesystem import safe_move


def load_job(logs_dir: Path, job_id: str) -> Job:
    """
    Loads a rollback job from the specified directory and job ID.

    This function attempts to locate and load a rollback job file in JSON format
    using the provided logs directory and job identifier. If the specified job
    file is not found, a FileNotFoundError is raised.

    Args:
        logs_dir (Path): The directory where rollback job files are stored.
        job_id (str): The identifier of the rollback job to load.

    Returns:
        Job: An instance of the Job class with data loaded from the job file.

    Raises:
        FileNotFoundError: If the job file cannot be found at the expected location.
    """
    job_path = logs_dir / "rollback" / f"job_{job_id}.json"
    if not job_path.exists():
        raise FileNotFoundError(f"No rollback job found for id '{job_id}' at {job_path}")  # noqa: TRY003
    return Job.model_validate(json.loads(job_path.read_text(encoding="utf-8")))


def save_job(logs_dir: Path, job: Job) -> Path:
    """
    Saves a job's data to a specified directory in JSON format.

    The function creates a "rollback" subdirectory within the given logs directory, if it does not
    already exist. It then writes the JSON representation of the job to a file within this subdirectory.

    Args:
        logs_dir (Path): The directory where the job data will be stored.
        job (Job): The job object to be saved. The object includes a `job_id` and a method to
            return its data in JSON format.

    Returns:
        Path: The path to the newly created JSON file that contains the job's data.
    """
    rollback_dir = logs_dir / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    job_path = rollback_dir / f"job_{job.job_id}.json"
    job_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job_path


def rollback_job(logs_dir: Path, job_id: str) -> list[AuditEvent]:
    """
    Reverses the changes made by a specific job, restoring original file paths and recording
    the rollback events. This function iterates through the list of moves associated with a job,
    starting from the most recent, and performs a safe rollback of file changes.

    Args:
        logs_dir (Path): The directory where job logs are stored.
        job_id (str): The unique identifier of the job to be rolled back.

    Returns:
        list[AuditEvent]: A list of audit events representing the rollback actions performed.
    """

    job = load_job(logs_dir, job_id)
    reversed_events: list[AuditEvent] = []
    for event in reversed(job.moves):
        if event.action == "move" and event.new_path is not None:
            safe_move(event.new_path, event.original_path)
            reversed_events.append(
                AuditEvent(original_path=event.new_path, new_path=event.original_path, action="rollback")
            )
    return reversed_events
