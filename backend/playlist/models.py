"""The data that moves between the analyser, planner and renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Track:
    """A track as the library knows it (from Plex, or a scanned folder)."""

    id: str  # Plex ratingKey, or a path hash for scanned folders
    library: str
    title: str
    artist: str
    album: str = ""
    genres: list[str] = field(default_factory=list)
    path: str = ""  # readable on this host
    duration_s: float = 0.0
    licence: str = ""
    licence_url: str = ""
    source_url: str = ""


@dataclass
class Analysis:
    """What the analyser found in a track's audio."""

    bpm: float
    beats: list[float]  # seconds
    downbeats: list[float]  # seconds: the first beat of each bar
    camelot: str | None
    key: str | None
    lufs: float
    energy: float  # 0-1, relative loudness/density
    mix_in_s: float  # first downbeat worth mixing in on
    mix_out_s: float  # last downbeat worth mixing out on
    # How clearly a regular kick confirms the beat grid (0 = not at all; the
    # planner skips tracks below MIN_GRID_CONFIDENCE).
    grid_confidence: float = 0.0
    version: int = 3


@dataclass
class PlanItem:
    track_id: str
    title: str
    artist: str
    library: str
    bpm: float
    camelot: str | None
    rate: float  # time-stretch factor: mix tempo / track tempo
    cue_in_s: float  # source seconds, on a downbeat
    cue_out_s: float  # source seconds, on a downbeat
    start_s: float = 0.0  # where it starts in the mix
    transition_beats: int = 32  # overlap with the next track

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    tempo_bpm: float
    items: list[PlanItem]
    duration_s: float
    genres: list[str] = field(default_factory=list)
    seed: int = 0

    def to_dict(self) -> dict:
        return {
            "tempo_bpm": round(self.tempo_bpm, 2),
            "duration_s": round(self.duration_s, 1),
            "genres": self.genres,
            "seed": self.seed,
            "tracks": [
                {
                    "id": i.track_id,
                    "title": i.title,
                    "artist": i.artist,
                    "library": i.library,
                    "bpm": round(i.bpm, 1),
                    "camelot": i.camelot,
                    "start_s": round(i.start_s, 1),
                }
                for i in self.items
            ],
        }
