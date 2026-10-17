"""SQLite store for the library index and per-track analysis."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from .models import Analysis, Track

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    library TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT NOT NULL DEFAULT '',
    genres TEXT NOT NULL DEFAULT '[]',
    path TEXT NOT NULL DEFAULT '',
    duration_s REAL NOT NULL DEFAULT 0,
    licence TEXT NOT NULL DEFAULT '',
    licence_url TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS tracks_library ON tracks(library);
CREATE TABLE IF NOT EXISTS analysis (
    id TEXT PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    data TEXT NOT NULL,
    version INTEGER NOT NULL,
    error TEXT
);
"""


class Cache:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()

    def upsert_tracks(self, tracks: Iterable[Track]) -> int:
        rows = [
            (
                t.id,
                t.library,
                t.title,
                t.artist,
                t.album,
                json.dumps(t.genres),
                t.path,
                t.duration_s,
                t.licence,
                t.licence_url,
                t.source_url,
            )
            for t in tracks
        ]
        with self._lock, self._db:
            self._db.executemany(
                """INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET library=excluded.library,
                   title=excluded.title, artist=excluded.artist, album=excluded.album,
                   genres=excluded.genres, path=excluded.path, duration_s=excluded.duration_s,
                   licence=excluded.licence, licence_url=excluded.licence_url,
                   source_url=excluded.source_url""",
                rows,
            )
        return len(rows)

    def remove_missing(self, library: str, keep_ids: set[str]) -> int:
        with self._lock, self._db:
            existing = {
                r[0]
                for r in self._db.execute("SELECT id FROM tracks WHERE library = ?", (library,))
            }
            gone = existing - keep_ids
            self._db.executemany("DELETE FROM tracks WHERE id = ?", [(g,) for g in gone])
        return len(gone)

    def tracks(self, libraries: Iterable[str] | None = None) -> list[Track]:
        sql, args = "SELECT * FROM tracks", []
        libs = list(libraries or [])
        if libs:
            sql += f" WHERE library IN ({','.join('?' * len(libs))})"
            args = libs
        with self._lock:
            return [_track(r) for r in self._db.execute(sql, args)]

    def track(self, track_id: str) -> Track | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return _track(r) if r else None

    def genres(self, libraries: Iterable[str] | None = None) -> list[tuple[str, int]]:
        counts = Counter(g for t in self.tracks(libraries) for g in t.genres)
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))

    def save_analysis(self, track_id: str, analysis: Analysis) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO analysis VALUES (?,?,?,NULL)",
                (track_id, json.dumps(asdict(analysis)), analysis.version),
            )

    def save_error(self, track_id: str, error: str, version: int) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO analysis VALUES (?,?,?,?)",
                (track_id, "{}", version, error[:500]),
            )

    def analysis(self, track_id: str) -> Analysis | None:
        with self._lock:
            r = self._db.execute(
                "SELECT data, error FROM analysis WHERE id = ?", (track_id,)
            ).fetchone()
        if not r or r[1]:
            return None
        return Analysis(**json.loads(r[0]))

    def pending(self, version: int, libraries: Iterable[str] | None = None) -> list[Track]:
        """Tracks with no analysis at this version (errors at this version count as done)."""
        with self._lock:
            done = {
                r[0]
                for r in self._db.execute("SELECT id FROM analysis WHERE version = ?", (version,))
            }
        return [t for t in self.tracks(libraries) if t.id not in done]

    def stats(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        with self._lock:
            rows = self._db.execute(
                """SELECT t.library, COUNT(*), COUNT(a.id) - COUNT(a.error), COUNT(a.error)
                   FROM tracks t LEFT JOIN analysis a ON a.id = t.id GROUP BY t.library"""
            ).fetchall()
        for lib, total, ok, err in rows:
            out[lib] = {"tracks": total, "analysed": ok, "failed": err}
        return out


def _track(r: tuple) -> Track:
    return Track(
        id=r[0],
        library=r[1],
        title=r[2],
        artist=r[3],
        album=r[4],
        genres=json.loads(r[5]),
        path=r[6],
        duration_s=r[7],
        licence=r[8],
        licence_url=r[9],
        source_url=r[10],
    )
