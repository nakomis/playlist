"""Render a plan to MP3s: level, stretch, beat-aligned bass-swap transitions.

Tracks are processed one at a time and the mix is streamed to a 16-bit PCM
scratch file, so memory stays at a track or two however long the mix is. Bar
starts outside the transitions are recorded as they go past; the split files
are cut at those, never inside a transition. Without gapless playback a cut is
heard as a tiny hiccup, and on the one of a steady bar it passes for the beat.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt

from . import audio
from .models import Plan, Track

SR = audio.SR
BASS_HZ = 200
MAX_GAIN_DB = 12.0

Progress = Callable[[float, str], None]


@dataclass
class OutputFile:
    name: str
    path: Path
    start_s: float
    duration_s: float


def segment_audio(track: Track, cue_in: float, cue_out: float) -> np.ndarray:
    """Decode just the cued part of a track (ffmpeg seeks sample-accurately)."""
    out = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-ss",
            f"{cue_in:.4f}",
            "-t",
            f"{cue_out - cue_in:.4f}",
            "-i",
            track.path,
            "-f",
            "f32le",
            "-ac",
            "2",
            "-ar",
            str(SR),
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(out, dtype=np.float32).reshape(-1, 2).copy()


def bass_swap(outgoing: np.ndarray, incoming: np.ndarray) -> np.ndarray:
    """Blend two equal-length, beat-aligned regions.

    Mids and highs crossfade across the whole overlap; the low end switches
    from one track to the other half-way (on a bar line, since the overlap is
    a whole number of bars), so two basslines never fight.
    """
    n = min(len(outgoing), len(incoming))
    outgoing, incoming = outgoing[:n], incoming[:n]
    sos = butter(4, BASS_HZ, btype="low", fs=SR, output="sos")
    out_low = sosfiltfilt(sos, outgoing, axis=0)
    in_low = sosfiltfilt(sos, incoming, axis=0)
    fade = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]
    # The swap itself takes 20 ms, to avoid a click.
    swap = np.zeros(n, dtype=np.float32)
    mid, w = n // 2, int(0.02 * SR)
    swap[mid + w // 2 :] = 1.0
    lo, hi = max(0, mid - w // 2), min(n, mid + w // 2)
    swap[lo:hi] = np.linspace(0.0, 1.0, hi - lo)
    swap = swap[:, None]
    highs = (outgoing - out_low) * (1 - fade) + (incoming - in_low) * fade
    lows = out_low * (1 - swap) + in_low * swap
    return (highs + lows).astype(np.float32)


def kick_envelope(x: np.ndarray, hop: int = 128) -> np.ndarray:
    """Sub-bass onset envelope of a stereo region (the kick, in dance music)."""
    from .analysis import _low_onset

    return _low_onset(x.mean(axis=1), SR, hop)


def align_offset(
    outgoing: np.ndarray, incoming: np.ndarray, beat_s: float, hop: int = 128
) -> tuple[int, float]:
    """Samples to delay `incoming` by so its kicks land on `outgoing`'s.

    Searches within half a beat either way, like a DJ nudging the platter.
    Returns (delay in samples, which may be negative; confidence 0-1). With
    confidence below about 0.3 there is no clear kick to go on, and the
    analysis grid alone decides.
    """
    a, b = kick_envelope(outgoing, hop), kick_envelope(incoming, hop)
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    max_lag = int(beat_s / 2 * SR / hop)
    lags = np.arange(-max_lag, max_lag + 1)
    scores = np.array(
        [np.dot(a[max(0, k) : n + min(0, k)], b[max(0, -k) : n - max(0, k)]) for k in lags]
    )
    i = int(np.argmax(scores))
    norm = np.sqrt(np.dot(a, a) * np.dot(b, b)) or 1.0
    return int(lags[i] * hop), float(max(0.0, scores[i] / norm))


def _shift(x: np.ndarray, delay: int) -> np.ndarray:
    """Delay (pad the front) or advance (trim the front) a region."""
    if delay > 0:
        return np.concatenate([np.zeros((delay, x.shape[1]), np.float32), x])
    return x[-delay:] if delay < 0 else x


def _limit(x: np.ndarray) -> np.ndarray:
    """Soft-knee limiter: transparent below 0.8, never past 1.0."""
    a = np.abs(x)
    over = a > 0.8
    if over.any():
        x = x.copy()
        x[over] = np.sign(x[over]) * (0.8 + 0.2 * np.tanh((a[over] - 0.8) / 0.2))
    return x


class _PcmWriter:
    def __init__(self, path: Path):
        self.f = path.open("wb")
        self.samples = 0

    def write(self, x: np.ndarray) -> None:
        pcm = (np.clip(_limit(x), -1, 1) * 32767).astype("<i2")
        self.f.write(pcm.tobytes())
        self.samples += len(x)

    def close(self) -> None:
        self.f.close()


def choose_cuts(candidates: list[int], total: int, segment: int) -> list[int]:
    """Pick bar starts to split at, about every `segment` samples.

    Each cut is the candidate nearest its target, at least 60% of a segment
    after the last; a final piece shorter than 40% of a segment is merged.
    """
    cuts: list[int] = []
    last = 0
    target = segment
    cands = sorted(c for c in candidates if 0 < c < total)
    while target < total - 0.4 * segment:
        options = [c for c in cands if c - last >= 0.6 * segment]
        if not options:
            break
        best = min(options, key=lambda c: abs(c - target))
        if total - best < 0.4 * segment:
            break
        cuts.append(best)
        last = best
        target = best + segment
    return cuts


def render(
    plan: Plan,
    tracks: dict[str, Track],
    lufs: dict[str, float],
    downbeats: dict[str, list[float]],
    out_dir: Path,
    title: str,
    *,
    split: bool = True,
    segment_minutes: float = 5.0,
    bitrate_kbps: int = 192,
    target_lufs: float = -14.0,
    progress: Progress | None = None,
) -> list[OutputFile]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = progress or (lambda f, m: None)
    beat_s = 60.0 / plan.tempo_bpm
    cut_candidates: list[int] = []
    tail: np.ndarray | None = None
    n_items = len(plan.items)

    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        pcm_path = Path(tmp) / "mix.pcm"
        writer = _PcmWriter(pcm_path)
        for i, item in enumerate(plan.items):
            report(0.85 * i / n_items, f"Mixing {item.artist} - {item.title}")
            track = tracks[item.track_id]
            seg = segment_audio(track, item.cue_in_s, item.cue_out_s)
            gain_db = min(MAX_GAIN_DB, target_lufs - lufs.get(item.track_id, target_lufs))
            seg *= np.float32(10 ** (gain_db / 20))
            seg = audio.time_stretch(seg, item.rate, SR)

            # Nudge the incoming track so its kicks sit on the outgoing ones;
            # this absorbs any residual analysis or stretching error.
            shift = 0
            if tail is not None:
                shift, conf = align_offset(tail, seg[: len(tail)], beat_s)
                if conf >= 0.3:
                    seg = _shift(seg, shift)
                else:
                    shift = 0
            head_len = len(tail) if tail is not None else 0
            next_len = int(round(item.transition_beats * beat_s * SR))
            next_len = min(next_len, max(0, len(seg) - head_len))
            seg_start = writer.samples - head_len  # where this track starts in the mix
            if tail is not None:
                writer.write(bass_swap(tail, seg[:head_len]))
            body_end = len(seg) - next_len
            body = seg[head_len:body_end]
            body_from, body_to = writer.samples, writer.samples + len(body)
            writer.write(body)
            tail = seg[body_end:] if next_len else None

            # Bar starts that fall in this track's solo stretch are safe cuts.
            for db in downbeats.get(item.track_id, []):
                if item.cue_in_s <= db <= item.cue_out_s:
                    pos = seg_start + shift + int(round((db - item.cue_in_s) / item.rate * SR))
                    if body_from + SR <= pos <= body_to - SR:
                        cut_candidates.append(pos)
        if tail is not None:
            writer.write(tail)
        writer.close()

        total = writer.samples
        cuts = choose_cuts(cut_candidates, total, int(segment_minutes * 60 * SR)) if split else []
        bounds = [0, *cuts, total]
        pcm = np.memmap(pcm_path, dtype="<i2", mode="r").reshape(-1, 2)
        files: list[OutputFile] = []
        parts = len(bounds) - 1
        for p in range(parts):
            a, b = bounds[p], bounds[p + 1]
            report(0.85 + 0.15 * p / parts, f"Encoding part {p + 1} of {parts}")
            name = f"{p + 1:02d} - {title}.mp3" if split and parts > 1 else f"{title}.mp3"
            path = out_dir / name
            tags = {
                "title": f"{title} (part {p + 1})" if parts > 1 else title,
                "artist": "Playlist",
                "album": title,
                "track": f"{p + 1}/{parts}",
            }
            _encode_s16(pcm[a:b], path, bitrate_kbps, tags)
            files.append(OutputFile(name, path, a / SR, (b - a) / SR))
        del pcm
    report(1.0, "Done")
    return files


def _encode_s16(pcm: np.ndarray, path: Path, bitrate_kbps: int, tags: dict[str, str]) -> None:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "s16le",
        "-ac",
        "2",
        "-ar",
        str(SR),
        "-i",
        "-",
        "-c:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate_kbps}k",
        "-id3v2_version",
        "3",
    ]
    for k, v in tags.items():
        cmd += ["-metadata", f"{k}={v}"]
    cmd.append(str(path))
    subprocess.run(cmd, input=np.ascontiguousarray(pcm).tobytes(), check=True, capture_output=True)
