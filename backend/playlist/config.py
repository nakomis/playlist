"""Settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    plex_url: str = "http://leia.local:32400"
    plex_token: str = ""
    # Where state lives: the analysis cache and rendered mixes. On Mace this is
    # a data volume, since the root filesystem is read-only.
    data_dir: Path = Path("data")
    # Plex reports paths as its container sees them (/data/music/...). Each
    # entry maps a Plex prefix to where the same files are mounted here.
    path_map: tuple[tuple[str, str], ...] = (("/data", "/mnt/plex"),)
    # Plex library titles we may draw from, and which of them are CC.
    libraries: tuple[str, ...] = ("Music", "Purchased")
    cc_libraries: tuple[str, ...] = ("Music",)
    bitrate_kbps: int = 192
    segment_minutes: float = 5.0
    target_lufs: float = -14.0
    retention_days: int = 7
    web_dist: Path | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "playlist.sqlite"

    @property
    def mixes_dir(self) -> Path:
        return self.data_dir / "mixes"

    def local_path(self, plex_path: str) -> Path:
        """Translate a path as Plex reports it into one readable here."""
        for prefix, local in self.path_map:
            if plex_path == prefix or plex_path.startswith(prefix.rstrip("/") + "/"):
                return Path(local + plex_path[len(prefix) :])
        return Path(plex_path)

    def is_cc(self, library: str) -> bool:
        return library in self.cc_libraries

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env

        def split(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            raw = e.get(name)
            return tuple(s.strip() for s in raw.split(",") if s.strip()) if raw else default

        path_map = cls.path_map
        if e.get("PLAYLIST_PATH_MAP"):
            pairs = [p.split("=", 1) for p in e["PLAYLIST_PATH_MAP"].split(",") if "=" in p]
            path_map = tuple((a.strip(), b.strip()) for a, b in pairs)
        web = e.get("PLAYLIST_WEB_DIST")
        return cls(
            plex_url=e.get("PLEX_URL", cls.plex_url),
            plex_token=e.get("PLEX_TOKEN", ""),
            data_dir=Path(e.get("PLAYLIST_DATA_DIR", "data")),
            path_map=path_map,
            libraries=split("PLAYLIST_LIBRARIES", cls.libraries),
            cc_libraries=split("PLAYLIST_CC_LIBRARIES", cls.cc_libraries),
            bitrate_kbps=int(e.get("PLAYLIST_BITRATE_KBPS", cls.bitrate_kbps)),
            segment_minutes=float(e.get("PLAYLIST_SEGMENT_MINUTES", cls.segment_minutes)),
            retention_days=int(e.get("PLAYLIST_RETENTION_DAYS", cls.retention_days)),
            web_dist=Path(web) if web else None,
        )
