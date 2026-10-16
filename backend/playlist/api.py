"""HTTP API and static front end."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .cache import Cache
from .config import Settings
from .jobs import Job, JobManager, MixRequest


class MixBody(BaseModel):
    genres: list[str] = Field(default_factory=list)
    duration_min: float = 60
    libraries: list[str] = Field(default_factory=list)
    output: str = "split"
    seed: int | None = None
    title: str | None = None
    bpm_min: float | None = None
    bpm_max: float | None = None


def library_list(settings: Settings, cache: Cache) -> list[dict]:
    stats = cache.stats()
    return [
        {
            "key": name,
            "title": name,
            "kind": "cc" if settings.is_cc(name) else "purchased",
            **stats.get(name, {"tracks": 0, "analysed": 0, "failed": 0}),
        }
        for name in settings.libraries
    ]


def job_view(job: Job, with_plan: bool = True) -> dict:
    d = job.public(with_plan)
    d["files"] = [{**f, "url": f"/api/mixes/{job.id}/files/{quote(f['name'])}"} for f in job.files]
    return d


def create_app(settings: Settings, cache: Cache, jobs: JobManager) -> FastAPI:
    app = FastAPI(title="Playlist", version=__version__)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/api/libraries")
    def libraries() -> list[dict]:
        return library_list(settings, cache)

    @app.get("/api/genres")
    def genres(libraries: str = Query("")) -> list[dict]:
        libs = [x for x in libraries.split(",") if x] or list(settings.libraries)
        return [{"name": g, "count": n} for g, n in cache.genres(libs)]

    @app.post("/api/mixes", status_code=201)
    def create_mix(body: MixBody) -> dict:
        try:
            job = jobs.submit(MixRequest(**body.model_dump()))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return job_view(job)

    @app.get("/api/mixes")
    def list_mixes() -> list[dict]:
        return [job_view(j, with_plan=False) for j in jobs.recent()]

    @app.get("/api/mixes/{job_id}")
    def get_mix(job_id: str) -> dict:
        return job_view(_job(jobs, job_id))

    @app.get("/api/mixes/{job_id}/files/{name}")
    def get_file(job_id: str, name: str) -> FileResponse:
        job = _job(jobs, job_id)
        if name not in {f["name"] for f in job.files}:
            raise HTTPException(404, "no such file")
        return FileResponse(jobs.mix_dir(job_id) / name, media_type="audio/mpeg", filename=name)

    @app.get("/api/mixes/{job_id}/zip")
    def get_zip(job_id: str) -> StreamingResponse:
        job = _job(jobs, job_id)
        if not job.files:
            raise HTTPException(409, "mix has no files yet")
        buf = io.BytesIO()
        # MP3s don't compress; store them, in play order.
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for f in job.files:
                z.write(jobs.mix_dir(job_id) / f["name"], f["name"])
        buf.seek(0)
        fname = quote(f"{job.title}.zip")
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
        )

    if settings.web_dist and Path(settings.web_dist, "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
    return app


def _job(jobs: JobManager, job_id: str) -> Job:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such mix")
    return job
