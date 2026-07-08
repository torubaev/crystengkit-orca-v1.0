from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


QUEUE_STATE_FILE = "orca_job_queue.json"
QUEUE_FILE_SUFFIXES = (".orcaqueue.json", ".queue.json")


@dataclass
class OrcaQueueJob:
    input_path: str
    output_path: str
    status: str = "queued"
    message: str = ""

    @property
    def name(self) -> str:
        return Path(self.input_path).name

    @property
    def folder(self) -> str:
        return str(Path(self.input_path).parent)


class OrcaJobQueue:
    def __init__(
        self,
        queues: Optional[Dict[str, Iterable[OrcaQueueJob]]] = None,
        active_queue: str = "Default",
    ):
        source = queues or {"Default": []}
        self.queues: Dict[str, List[OrcaQueueJob]] = {
            self._clean_queue_name(name): list(jobs)
            for name, jobs in source.items()
        }
        if not self.queues:
            self.queues = {"Default": []}
        self.active_queue = self._clean_queue_name(active_queue)
        if self.active_queue not in self.queues:
            self.active_queue = next(iter(self.queues))
        self.current_index: Optional[int] = None
        self.current_queue: Optional[str] = None

    @staticmethod
    def _clean_queue_name(name: str) -> str:
        cleaned = str(name or "").strip()
        return cleaned or "Default"

    @property
    def jobs(self) -> List[OrcaQueueJob]:
        return self.queues.setdefault(self.active_queue, [])

    def __len__(self) -> int:
        return len(self.jobs)

    def __bool__(self) -> bool:
        return bool(self.jobs)

    def clear_finished_state(self):
        for jobs in self.queues.values():
            for job in jobs:
                if job.status in {"running", "stopped"}:
                    job.status = "queued"
                    job.message = ""
        self.current_index = None
        self.current_queue = None

    def queue_names(self) -> List[str]:
        return list(self.queues.keys())

    def set_active_queue(self, name: str):
        cleaned = self._clean_queue_name(name)
        if cleaned not in self.queues:
            self.queues[cleaned] = []
        self.active_queue = cleaned

    def create_queue(self, name: str):
        self.set_active_queue(name)

    def delete_active_queue(self):
        if len(self.queues) <= 1:
            self.queues[self.active_queue] = []
            self.current_index = None
            self.current_queue = None
            return
        self.queues.pop(self.active_queue, None)
        self.active_queue = next(iter(self.queues))
        self.current_index = None
        self.current_queue = None

    def add_input_files(self, paths: Iterable[str]) -> int:
        added = 0
        seen = {str(Path(job.input_path).resolve()).lower() for job in self.jobs}
        for raw_path in paths:
            path = Path(raw_path).expanduser()
            if path.suffix.lower() != ".inp" or not path.is_file():
                continue
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            self.jobs.append(
                OrcaQueueJob(
                    input_path=str(path),
                    output_path=str(path.with_suffix(".out")),
                )
            )
            seen.add(key)
            added += 1
        return added

    def remove_indices(self, indices: Iterable[int]):
        blocked = set(indices)
        self.jobs = [job for idx, job in enumerate(self.jobs) if idx not in blocked]
        self.current_index = None
        self.current_queue = None

    def reset_pending(self):
        for job in self.jobs:
            if job.status in {"done", "failed", "stopped"}:
                job.status = "queued"
                job.message = ""
        self.current_index = None

    def next_queued(self) -> Optional[OrcaQueueJob]:
        for idx, job in enumerate(self.jobs):
            if job.status == "queued":
                self.current_index = idx
                self.current_queue = self.active_queue
                job.status = "running"
                job.message = ""
                return job
        self.current_index = None
        self.current_queue = None
        return None

    def mark_current(self, status: str, message: str = ""):
        if self.current_index is None:
            return
        jobs = self.queues.get(self.current_queue or self.active_queue, [])
        if 0 <= self.current_index < len(jobs):
            jobs[self.current_index].status = status
            jobs[self.current_index].message = message
        self.current_index = None
        self.current_queue = None

    def summary(self) -> str:
        counts = {}
        for job in self.jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        return ", ".join(f"{status}: {count}" for status, count in sorted(counts.items())) or "empty"

    def to_json(self) -> str:
        payload = {
            "active_queue": self.active_queue,
            "queues": {
                name: [asdict(job) for job in jobs]
                for name, jobs in self.queues.items()
            },
        }
        return json.dumps(payload, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "OrcaJobQueue":
        payload = json.loads(text)
        if "queues" in payload:
            queues = {
                name: [OrcaQueueJob(**item) for item in jobs]
                for name, jobs in payload.get("queues", {}).items()
            }
            return cls(queues, payload.get("active_queue", "Default"))
        jobs = [OrcaQueueJob(**item) for item in payload.get("jobs", [])]
        return cls({"Default": jobs}, "Default")

    def save(self, path: Path):
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "OrcaJobQueue":
        if not path.is_file():
            return cls()
        queue = cls.from_json(path.read_text(encoding="utf-8", errors="replace"))
        queue.clear_finished_state()
        return queue

    @classmethod
    def looks_like_queue_file(cls, path: Path) -> bool:
        if not path.is_file() or path.suffix.lower() != ".json":
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return False
        return isinstance(payload, dict) and ("queues" in payload or "jobs" in payload)
