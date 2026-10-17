"""Per-track audio analysis: tempo, beats, bars, key, loudness, mix points.

Version 1 uses librosa throughout. Beat tracking is good on four-to-the-floor
music; bar starts (downbeats) are inferred by choosing, of the four possible
phases, the one whose beats carry the most low-frequency onset energy, which
is where the kick and bass land on the one. PLAY-2 tracks swapping in
Essentia or allin1 if this proves too rough on real tracks.
"""

from __future__ import annotations

import numpy as np

from . import audio, camelot
from .models import Analysis

VERSION = 3
SR = 22050
BEATS_PER_BAR = 4

# Krumhansl-Schmuckler key profiles.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def analyse_file(path: str) -> Analysis:
    y = audio.decode(path, sr=SR, channels=1)[:, 0]
    return analyse_signal(y, SR)


def analyse_signal(y: np.ndarray, sr: int = SR) -> Analysis:
    import librosa
    import pyloudnorm

    if len(y) < sr * 10:
        raise ValueError("track shorter than 10 s")

    hop = 512
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=hop)
    bpm = float(np.atleast_1d(tempo)[0])
    beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    if len(beats) < 16 or bpm <= 0:
        raise ValueError("no steady beat found")
    duration = len(y) / sr
    beats, bpm = fit_grid(beats, 60.0 / bpm, duration)
    low_hop = 64
    low = _low_onset(y, sr, low_hop)
    period, phase, sharpness = refine_tempo(low, sr, low_hop, 60.0 / bpm)
    confidence = sharpness
    if sharpness >= KICK_SHARPNESS:
        # A clear, regular kick: trust it over the general beat tracker.
        bpm = 60.0 / period
        beats = phase + period * np.arange(
            int(np.ceil(-phase / period)), int((duration - phase) / period) + 1
        )

    downbeats = _downbeats(low, sr, beats, low_hop)
    pitch, minor = _key(y, sr)
    lufs = float(pyloudnorm.Meter(sr).integrated_loudness(y.astype(np.float64)))

    # Energy per bar: where the track is "properly going", for picking mix points.
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    bar_energy = _bar_energy(rms, rms_t, downbeats)
    mix_in, mix_out = _mix_points(downbeats, bar_energy)
    energy = float(np.clip(np.median(bar_energy) / (np.max(rms) + 1e-9), 0, 1))

    return Analysis(
        bpm=round(bpm, 3),
        beats=[round(float(b), 4) for b in beats],
        downbeats=[round(float(d), 4) for d in downbeats],
        camelot=camelot.to_camelot(pitch, minor),
        key=camelot.key_name(pitch, minor),
        lufs=round(lufs, 2) if np.isfinite(lufs) else -70.0,
        energy=round(energy, 3),
        mix_in_s=round(float(mix_in), 4),
        mix_out_s=round(float(mix_out), 4),
        grid_confidence=round(float(confidence), 3),
        version=VERSION,
    )


def fit_grid(beats: np.ndarray, period: float, duration: float) -> tuple[np.ndarray, float]:
    """Fit a fixed-tempo grid through the tracked beats.

    The tracker's beats are snapped to analysis frames (~12-23 ms), so their
    spacing jitters and a tempo taken from it is quantised. Electronic music
    holds a fixed tempo, so a least-squares line through every beat (beat
    number against time) gives the period to well under a millisecond, and the
    grid it implies is steadier than the beats it came from. Skipped or extra
    beats are handled by numbering beats from the estimated period, and beats
    far off the line are dropped before the final fit.
    """
    # Number each beat from the gap to its neighbour, not from the first beat:
    # a rough period then only has to be right to within half a beat per gap,
    # rather than accumulating over hundreds of beats.
    gaps = np.maximum(1, np.round(np.diff(beats) / period))
    k = np.concatenate([[0], np.cumsum(gaps)])
    slope, intercept = np.polyfit(k, beats, 1)
    for _ in range(2):
        resid = beats - (intercept + slope * k)
        keep = np.abs(resid) < 0.15 * slope
        if keep.sum() < 16:
            break
        slope, intercept = np.polyfit(k[keep], beats[keep], 1)
    period, b0 = float(slope), float(intercept)
    first = int(np.ceil(-b0 / period))
    last = int(np.floor((duration - b0) / period))
    grid = b0 + period * np.arange(first, last + 1)
    return grid[grid >= 0], 60.0 / period


def _low_onset(y: np.ndarray, sr: int, hop: int, cutoff: float = 90.0) -> np.ndarray:
    """Rises in sub-bass energy: in dance music, overwhelmingly the kick.

    Linear power, not decibels: on a log scale a bass note's onset scores much
    like a kick's, and trance basslines sit on the off-beats.
    """
    from scipy.signal import butter, sosfiltfilt

    sos = butter(4, cutoff, btype="low", fs=sr, output="sos")
    sub = sosfiltfilt(sos, y)
    n = len(sub) // hop
    power = (sub[: n * hop].reshape(n, hop) ** 2).mean(axis=1)
    env = np.sqrt(power)
    return np.clip(np.diff(env, prepend=env[:1]), 0, None)


def kick_phase(
    beats: np.ndarray, period: float, low: np.ndarray, sr: int, hop: int
) -> tuple[float, float]:
    """Where in the beat the kick lands (seconds, -period/2..period/2), and how sharply.

    Folds the low-end onset envelope at the beat period. A sharp peak (ratio
    well above 1) means the period is right and the kick is regular.
    """
    t = np.arange(len(low)) * hop / sr
    phase = ((t - beats[0]) % period) / period
    hist, edges = np.histogram(phase, bins=64, weights=low)
    peak = edges[int(np.argmax(hist))] + 0.5 / 64
    offset = (peak if peak < 0.5 else peak - 1) * period
    return offset, float(hist.max() / (hist.mean() + 1e-9))


KICK_SHARPNESS = 0.5  # kick peak at least 1.5x the average


def refine_tempo(
    low: np.ndarray, sr: int, hop: int, period: float, span: float = 0.03, step_bpm: float = 0.005
) -> tuple[float, float, float]:
    """Search for the beat period on which the kick lines up best.

    For each candidate period, the low-end onset envelope is wrapped round a
    circle (one turn per beat); a regular kick piles its weight up at one
    angle. The length of the weighted mean vector (0 for none, 1 for a perfect
    pulse) scores the candidate, and its angle gives the phase. Returns
    (period, phase in seconds, sharpness); the general beat tracker is only
    overruled when sharpness clears KICK_SHARPNESS.
    """
    w = np.clip(low - np.median(low), 0, None)
    if w.sum() <= 0:
        return period, 0.0, 0.0
    t = np.arange(len(low)) * hop / sr
    bpm0 = 60.0 / period
    bins = 48
    best = (0.0, period, 0.0)
    for bpm in np.arange(bpm0 * (1 - span), bpm0 * (1 + span), step_bpm):
        p = 60.0 / bpm
        idx = ((t / p) % 1.0 * bins).astype(int)
        hist = np.bincount(idx, weights=w, minlength=bins)
        # Peak height over the mean, measured on a 3-bin window so a peak
        # straddling two bins isn't penalised.
        smooth = hist + np.roll(hist, 1) + np.roll(hist, -1)
        k = int(np.argmax(smooth))
        score = smooth[k] / (3 * hist.mean()) - 1
        if score > best[0]:
            # Sub-bin phase: weighted circular mean over the peak's window.
            win = np.arange(k - 2, k + 3)
            ang = 2 * np.pi * (win + 0.5) / bins
            z = (hist[win % bins] * np.exp(1j * ang)).sum()
            best = (float(score), p, (np.angle(z) / (2 * np.pi)) % 1.0 * p)
    score, p, phase = best
    return p, phase, score


def _downbeats(low: np.ndarray, sr: int, beats: np.ndarray, hop: int) -> np.ndarray:
    import librosa

    frames = np.clip(librosa.time_to_frames(beats, sr=sr, hop_length=hop), 0, len(low) - 1)
    strength = low[frames]
    scores = [strength[p::BEATS_PER_BAR].mean() for p in range(BEATS_PER_BAR)]
    phase = int(np.argmax(scores))
    return beats[phase::BEATS_PER_BAR]


def _key(y: np.ndarray, sr: int) -> tuple[int, bool]:
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    best, best_score = (0, False), -np.inf
    for pc in range(12):
        for minor, profile in ((False, _MAJOR), (True, _MINOR)):
            score = np.corrcoef(chroma, np.roll(profile, pc))[0, 1]
            if score > best_score:
                best, best_score = (pc, minor), score
    return best


def _bar_energy(rms: np.ndarray, rms_t: np.ndarray, downbeats: np.ndarray) -> np.ndarray:
    edges = np.append(downbeats, rms_t[-1])
    out = []
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        seg = rms[(rms_t >= a) & (rms_t < b)]
        out.append(float(seg.mean()) if len(seg) else 0.0)
    return np.array(out)


def _mix_points(downbeats: np.ndarray, bar_energy: np.ndarray) -> tuple[float, float]:
    """First and last bars where the track is near its typical level.

    Mixing in after a long ambient intro, and out before a long fade, keeps the
    energy up; the renderer still overlaps whole phrases around these points.
    """
    if len(downbeats) < 8:
        return float(downbeats[0]), float(downbeats[-1])
    level = 0.6 * np.median(bar_energy)
    loud = np.flatnonzero(bar_energy >= level)
    first = int(loud[0]) if len(loud) else 0
    last = int(loud[-1]) + 1 if len(loud) else len(downbeats) - 1
    # Snap to 8-bar phrases from the first loud bar, and never past the end.
    last = min(len(downbeats) - 1, first + ((last - first) // 8) * 8)
    if last <= first:
        first, last = 0, len(downbeats) - 1
    return float(downbeats[first]), float(downbeats[last])
