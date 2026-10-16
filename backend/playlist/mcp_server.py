"""MCP server: the same operations as the web API, for Claude sessions.

Served over streamable HTTP on its own port, behind its own mTLS vhost.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import planner
from .api import job_view, library_list
from .cache import Cache
from .config import Settings
from .jobs import JobManager, MixRequest


def create_mcp(
    settings: Settings, cache: Cache, jobs: JobManager, *, host: str = "0.0.0.0", port: int = 8001
) -> FastMCP:
    mcp = FastMCP(
        "playlist",
        host=host,
        port=port,
        instructions=(
            "Builds beat-matched continuous mixes from the Plex libraries. 'Music' is Creative "
            "Commons; 'Purchased' is bought music and makes a mix private. Typical use: "
            "list_genres, preview_plan, then create_mix and poll get_mix until done."
        ),
    )

    @mcp.tool()
    def list_libraries() -> list[dict]:
        """The Plex libraries Playlist can draw from, with track and analysis counts."""
        return library_list(settings, cache)

    @mcp.tool()
    def list_genres(libraries: list[str] | None = None) -> list[dict]:
        """Genres in the given libraries (all by default), with track counts."""
        return [{"name": g, "count": n} for g, n in cache.genres(libraries or None)]

    @mcp.tool()
    def find_tracks(
        genre: str | None = None,
        libraries: list[str] | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Analysed tracks matching a genre and BPM range (BPM, key, energy, length)."""
        out = []
        for t in cache.tracks(libraries or None):
            if genre and genre.lower() not in (g.lower() for g in t.genres):
                continue
            a = cache.analysis(t.id)
            if not a or (bpm_min and a.bpm < bpm_min) or (bpm_max and a.bpm > bpm_max):
                continue
            out.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "artist": t.artist,
                    "library": t.library,
                    "genres": t.genres,
                    "bpm": round(a.bpm, 1),
                    "camelot": a.camelot,
                    "energy": a.energy,
                    "duration_s": round(t.duration_s),
                }
            )
            if len(out) >= limit:
                break
        return out

    @mcp.tool()
    def preview_plan(
        duration_min: float,
        genres: list[str] | None = None,
        libraries: list[str] | None = None,
        seed: int = 0,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
    ) -> dict:
        """Plan a mix without rendering it: the ordered tracks, tempo and length."""
        libs = libraries or list(settings.libraries)
        cands = [planner.Candidate(t, a) for t in cache.tracks(libs) if (a := cache.analysis(t.id))]
        try:
            plan = planner.plan_mix(
                cands,
                planner.PlanRequest(
                    duration_s=duration_min * 60,
                    genres=genres or [],
                    libraries=libs,
                    seed=seed,
                    bpm_min=bpm_min,
                    bpm_max=bpm_max,
                ),
            )
        except planner.PlanError as e:
            return {"error": str(e)}
        return plan.to_dict()

    @mcp.tool()
    def create_mix(
        duration_min: float,
        genres: list[str] | None = None,
        libraries: list[str] | None = None,
        output: str = "split",
        seed: int | None = None,
        title: str | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
    ) -> dict:
        """Queue a mix for rendering. output is 'split' (~5-min files) or 'single'."""
        job = jobs.submit(
            MixRequest(
                genres=genres or [],
                duration_min=duration_min,
                libraries=libraries or [],
                output=output,
                seed=seed,
                title=title,
                bpm_min=bpm_min,
                bpm_max=bpm_max,
            )
        )
        return job_view(job)

    @mcp.tool()
    def get_mix(mix_id: str) -> dict:
        """A mix's status, plan, files (with download URLs) and licence manifest."""
        job = jobs.get(mix_id)
        return job_view(job) if job else {"error": "no such mix"}

    @mcp.tool()
    def list_mixes() -> list[dict]:
        """Recent mixes, newest first."""
        return [job_view(j, with_plan=False) for j in jobs.recent()]

    return mcp
