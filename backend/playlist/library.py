"""Index the Plex libraries into the cache, and analyse what's new.

Plex gives us titles, artists, genres and file paths, one section per
library. Genres usually live on albums and artists rather than tracks, so they
are inherited downwards. CC tracks get their licence from the `tracks.json`
sidecar the FMA crawl writes; failing a Plex genre, a `cc-<genre>` folder name
stands in.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import httpx

from . import analysis
from .cache import Cache
from .config import Settings
from .models import Track

log = logging.getLogger(__name__)


class PlexClient:
    def __init__(self, url: str, token: str, client: httpx.Client | None = None):
        self.http = client or httpx.Client(base_url=url, timeout=120)
        self.http.headers.update({"Accept": "application/json", "X-Plex-Token": token})

    def _get(self, path: str, **params) -> dict:
        r = self.http.get(path, params=params)
        r.raise_for_status()
        return r.json()["MediaContainer"]

    def sections(self) -> list[dict]:
        return [
            d
            for d in self._get("/library/sections").get("Directory", [])
            if d.get("type") == "artist"
        ]

    def items(self, section_key: str, plex_type: int) -> list[dict]:
        return self._get(f"/library/sections/{section_key}/all", type=plex_type).get("Metadata", [])


def _tags(meta: dict, field: str = "Genre") -> list[str]:
    return [g["tag"] for g in meta.get(field, []) if g.get("tag")]


def _folder_genre(path: str) -> list[str]:
    for part in Path(path).parts:
        if part.lower().startswith("cc-") and len(part) > 3:
            return [part[3:].replace("-", " ").title()]
    return []


class LicenceIndex:
    """Looks up a CC file's licence in the nearest tracks.json above it."""

    def __init__(self) -> None:
        self._cache: dict[Path, dict[str, dict] | None] = {}

    def lookup(self, path: str) -> dict:
        p = Path(path)
        for d in p.parents:
            if d not in self._cache:
                f = d / "tracks.json"
                try:
                    rows = json.loads(f.read_text()) if f.is_file() else None
                except (OSError, ValueError):
                    rows = None
                self._cache[d] = {r["file"]: r for r in rows} if rows else None
            idx = self._cache[d]
            if idx is not None:
                return idx.get(str(p.relative_to(d)), {})
        return {}


def sync_plex(settings: Settings, cache: Cache, plex: PlexClient | None = None) -> dict[str, int]:
    plex = plex or PlexClient(settings.plex_url, settings.plex_token)
    licences = LicenceIndex()
    counts: dict[str, int] = {}
    for section in plex.sections():
        title = section["title"]
        if title not in settings.libraries:
            continue
        key = str(section["key"])
        artist_genres = {str(a["ratingKey"]): _tags(a) for a in plex.items(key, 8)}
        album_genres = {str(a["ratingKey"]): _tags(a) for a in plex.items(key, 9)}
        tracks = []
        for m in plex.items(key, 10):
            try:
                plex_path = m["Media"][0]["Part"][0]["file"]
            except (KeyError, IndexError):
                continue
            path = str(settings.local_path(plex_path))
            genres = (
                _tags(m)
                or album_genres.get(str(m.get("parentRatingKey")), [])
                or artist_genres.get(str(m.get("grandparentRatingKey")), [])
                or _folder_genre(plex_path)
            )
            lic = licences.lookup(path) if settings.is_cc(title) else {}
            tracks.append(
                Track(
                    id=str(m["ratingKey"]),
                    library=title,
                    title=m.get("title", "?"),
                    artist=m.get("originalTitle") or m.get("grandparentTitle", "?"),
                    album=m.get("parentTitle", ""),
                    genres=sorted(set(genres)),
                    path=path,
                    duration_s=m.get("duration", 0) / 1000,
                    licence=lic.get("licence", ""),
                    licence_url=lic.get("licence_url", ""),
                    source_url=lic.get("source_url", ""),
                )
            )
        cache.upsert_tracks(tracks)
        removed = cache.remove_missing(title, {t.id for t in tracks})
        counts[title] = len(tracks)
        log.info("synced %s: %d tracks (%d removed)", title, len(tracks), removed)
    return counts


def scan_folder(folder: Path, library: str, cache: Cache, genre: str | None = None) -> int:
    """Index a plain folder of audio files: for development without Plex."""
    import hashlib

    from mutagen import File as MutagenFile

    licences = LicenceIndex()
    tracks = []
    for f in sorted(folder.rglob("*")):
        if f.suffix.lower() not in {".mp3", ".flac", ".m4a", ".ogg", ".wav"}:
            continue
        tags = MutagenFile(f, easy=True) or {}
        lic = licences.lookup(str(f))
        tracks.append(
            Track(
                id="f" + hashlib.sha1(str(f).encode()).hexdigest()[:16],
                library=library,
                title=(tags.get("title") or [lic.get("title") or f.stem])[0],
                artist=(tags.get("artist") or [lic.get("artist") or "?"])[0],
                album=(tags.get("album") or [lic.get("album", "")])[0],
                genres=[genre] if genre else list(tags.get("genre") or _folder_genre(str(f))),
                path=str(f),
                licence=lic.get("licence", ""),
                licence_url=lic.get("licence_url", ""),
                source_url=lic.get("source_url", ""),
            )
        )
    cache.upsert_tracks(tracks)
    return len(tracks)


def _analyse_one(track_id: str, path: str):
    try:
        return track_id, analysis.analyse_file(path), None
    except Exception as e:  # noqa: BLE001 - one bad file must not stop a batch
        return track_id, None, f"{type(e).__name__}: {e}"


def analyse_pending(
    cache: Cache,
    libraries: Iterable[str] | None = None,
    *,
    workers: int = 2,
    limit: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    pending = cache.pending(analysis.VERSION, libraries)[:limit]
    done = failed = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_analyse_one, t.id, t.path) for t in pending]
        for fut in as_completed(futures):
            tid, result, err = fut.result()
            if result is not None:
                cache.save_analysis(tid, result)
                done += 1
            else:
                cache.save_error(tid, err or "unknown", analysis.VERSION)
                failed += 1
                log.warning("analysis failed for %s: %s", tid, err)
            if progress:
                progress(done + failed, len(pending))
    return {"analysed": done, "failed": failed, "pending": len(pending) - done - failed}
