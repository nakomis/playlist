from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from playlist import audio
from playlist.models import Analysis, Track

SR = 44100


def click_track(
    bpm: float, seconds: float, sr: int = SR, offset: float = 0.0, pitch: float = 220.0
) -> np.ndarray:
    """A four-to-the-floor kick (decaying 55 Hz thump) over a quiet tone, stereo."""
    n = int(seconds * sr)
    t = np.arange(n) / sr
    y = 0.05 * np.sin(2 * np.pi * pitch * t)
    period = 60.0 / bpm
    kick_len = int(0.12 * sr)
    kt = np.arange(kick_len) / sr
    kick = 0.9 * np.sin(2 * np.pi * 55 * kt) * np.exp(-kt * 30)
    b = offset
    while b < seconds:
        i = int(b * sr)
        j = min(n, i + kick_len)
        y[i:j] += kick[: j - i]
        b += period
    return np.stack([y, y], axis=1).astype(np.float32)


@pytest.fixture
def make_mp3(tmp_path: Path):
    def make(name: str, bpm: float, seconds: float, **kw) -> Path:
        path = tmp_path / f"{name}.mp3"
        audio.encode_mp3(click_track(bpm, seconds, **kw), path, tags={"title": name})
        return path

    return make


def fake_analysis(
    bpm: float,
    seconds: float,
    camelot: str = "8A",
    energy: float = 0.7,
    lufs: float = -12.0,
    confidence: float = 1.0,
) -> Analysis:
    period = 60.0 / bpm
    beats = list(np.arange(0, seconds, period))
    downbeats = beats[::4]
    return Analysis(
        bpm=bpm,
        beats=beats,
        downbeats=downbeats,
        camelot=camelot,
        key="Am",
        lufs=lufs,
        energy=energy,
        mix_in_s=downbeats[2],
        mix_out_s=downbeats[-3],
        grid_confidence=confidence,
    )


def fake_track(
    i: int, library: str = "Music", genres=("Trance",), artist: str | None = None, path: str = ""
) -> Track:
    return Track(
        id=f"t{i}",
        library=library,
        title=f"Track {i}",
        artist=artist or f"Artist {i}",
        genres=list(genres),
        path=path,
        licence="CC BY 4.0" if library == "Music" else "",
        source_url=f"https://example.org/{i}",
    )


def have_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False
