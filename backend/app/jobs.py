import threading
import uuid
from dataclasses import dataclass
from typing import Optional

_lock = threading.Lock()
_jobs: dict[str, "Job"] = {}


@dataclass
class Job:
    status: str = "separating"
    result: Optional[dict] = None
    detail: Optional[str] = None


def create_job() -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = Job()
    return job_id


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def set_status(job_id: str, status: str) -> None:
    with _lock:
        _jobs[job_id].status = status


def set_result(job_id: str, result: dict) -> None:
    with _lock:
        job = _jobs[job_id]
        job.status = "done"
        job.result = result


def set_failed(job_id: str, detail: str) -> None:
    with _lock:
        job = _jobs[job_id]
        job.status = "failed"
        job.detail = detail
