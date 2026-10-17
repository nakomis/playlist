"""Mix jobs: plan, render and record, one at a time on a worker thread.

Mace has four cores and rendering is heavy, so mixes queue rather than run in
parallel. Each mix lives in its own folder with a job.json beside the files,
so state survives a restart; anything older than the retention period is
deleted.
"""

from __future__ import annotations

import json
import logging
import queue
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import manifest, planner, renderer
from .cache import Cache
from .config import Settings

log = logging.getLogger(__name__)


@dataclass
class MixRequest:
    genres: list[str]
    duration_min: float
    libraries: list[str]
    output: str = "split"  # or "single"
    seed: int | None = None
    title: str | None = None
    bpm_min: float | None = None
    bpm_max: float | None = None


@dataclass
class Job:
    id: str
    request: dict
    title: str
    created_at: float
    status: str = "queued"  # queued, planning, rendering, done, failed
    progress: float = 0.0
    message: str = "Waiting"
    error: str | None = None
    plan: dict | None = None
    files: list[dict] = field(default_factory=list)
    manifest: dict | None = None

    def public(self, with_plan: bool = True) -> dict:
        d = asdict(self)
        d["genres"] = self.request.get("genres", [])
        if not with_plan:
            d.pop("plan")
        return d


class JobManager:
    def __init__(self, settings: Settings, cache: Cache):
        self.settings = settings
        self.cache = cache
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        settings.mixes_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        for f in self.settings.mixes_dir.glob("*/job.json"):
            try:
                job = Job(**json.loads(f.read_text()))
            except (ValueError, TypeError):
                continue
            if job.status not in ("done", "failed"):
                job.status, job.error = "failed", "interrupted by a restart"
            self.jobs[job.id] = job

    def start(self) -> None:
        if not self._thread:
            self._thread = threading.Thread(target=self._run, name="mix-worker", daemon=True)
            self._thread.start()

    def submit(self, req: MixRequest) -> Job:
        if req.output not in ("split", "single"):
            raise ValueError("output must be 'split' or 'single'")
        if not 5 <= req.duration_min <= 600:
            raise ValueError("duration must be between 5 and 600 minutes")
        unknown = set(req.libraries) - set(self.settings.libraries)
        if unknown:
            raise ValueError(f"unknown libraries: {', '.join(sorted(unknown))}")
        if req.seed is None:
            req.seed = int(time.time()) % 100000
        genres = ", ".join(req.genres) if req.genres else "Mixed"
        title = req.title or f"{genres} mix {time.strftime('%Y-%m-%d')} #{req.seed}"
        job = Job(
            id=uuid.uuid4().hex[:12],
            request=asdict(req),
            title=_safe(title),
            created_at=time.time(),
        )
        with self._lock:
            self.jobs[job.id] = job
        self._save(job)
        self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[Job]:
        return sorted(self.jobs.values(), key=lambda j: -j.created_at)[:limit]

    def mix_dir(self, job_id: str) -> Path:
        return self.settings.mixes_dir / job_id

    def purge_old(self) -> int:
        cutoff = time.time() - self.settings.retention_days * 86400
        old = [j for j in self.jobs.values() if j.created_at < cutoff]
        for j in old:
            shutil.rmtree(self.mix_dir(j.id), ignore_errors=True)
            self.jobs.pop(j.id, None)
        return len(old)

    def _save(self, job: Job) -> None:
        d = self.mix_dir(job.id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "job.json").write_text(json.dumps(asdict(job), indent=1))

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.jobs.get(job_id)
            if job:
                self.process(job)

    def process(self, job: Job) -> None:
        req = MixRequest(**job.request)
        try:
            job.status, job.message = "planning", "Choosing tracks"
            self._save(job)
            libs = req.libraries or list(self.settings.libraries)
            tracks = {t.id: t for t in self.cache.tracks(libs)}
            cands = []
            for t in tracks.values():
                a = self.cache.analysis(t.id)
                if a:
                    cands.append(planner.Candidate(t, a))
            plan = planner.plan_mix(
                cands,
                planner.PlanRequest(
                    duration_s=req.duration_min * 60,
                    genres=req.genres,
                    libraries=libs,
                    seed=req.seed or 0,
                    bpm_min=req.bpm_min,
                    bpm_max=req.bpm_max,
                ),
            )
            job.plan = plan.to_dict()
            job.manifest = manifest.build_manifest(plan, tracks, self.settings.cc_libraries)
            job.status = "rendering"
            self._save(job)

            analyses = {i.track_id: self.cache.analysis(i.track_id) for i in plan.items}

            def progress(frac: float, msg: str) -> None:
                job.progress, job.message = round(frac, 3), msg

            files = renderer.render(
                plan,
                tracks,
                {k: a.lufs for k, a in analyses.items() if a},
                {k: a.downbeats for k, a in analyses.items() if a},
                self.mix_dir(job.id),
                job.title,
                split=req.output == "split",
                segment_minutes=self.settings.segment_minutes,
                bitrate_kbps=self.settings.bitrate_kbps,
                target_lufs=self.settings.target_lufs,
                progress=progress,
            )
            job.files = [
                {
                    "name": f.name,
                    "size": f.path.stat().st_size,
                    "start_s": round(f.start_s, 2),
                    "duration_s": round(f.duration_s, 2),
                }
                for f in files
            ]
            job.status, job.progress, job.message = "done", 1.0, "Ready"
        except planner.PlanError as e:
            job.status, job.error, job.message = "failed", str(e), str(e)
        except Exception as e:  # noqa: BLE001 - report, never kill the worker
            log.exception("mix %s failed", job.id)
            job.status, job.error, job.message = "failed", f"{type(e).__name__}: {e}", "Failed"
        self._save(job)


def _safe(name: str) -> str:
    """A title that is also a valid FAT32 filename."""
    bad = '<>:"/\\|?*'
    return "".join("-" if c in bad else c for c in name).strip(" .")[:80] or "mix"
