"""Deterministic mix planning: choose and order tracks for a requested length.

No LLM. Each step picks the candidate that best continues the mix, scoring
harmonic compatibility (Camelot), tempo closeness, the energy curve
(warm up, hold, wind down) and a little seeded jitter so a reroll differs.
The whole mix plays at one tempo: the median of the chosen tracks, so each
is stretched by a few per cent at most.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from statistics import median

from . import camelot
from .models import Analysis, Plan, PlanItem, Track

MAX_STRETCH = 0.08  # never stretch a track more than 8%
DEFAULT_TRANSITION_BEATS = 32  # eight bars of overlap
MIN_SEGMENT_BEATS = 64  # a track must contribute at least 16 bars of its own
MIN_GRID_CONFIDENCE = 0.5  # below this the beat grid can't be trusted to mix on


class PlanError(ValueError):
    pass


@dataclass
class PlanRequest:
    duration_s: float
    genres: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    seed: int = 0
    bpm_min: float | None = None
    bpm_max: float | None = None
    transition_beats: int = DEFAULT_TRANSITION_BEATS


@dataclass
class Candidate:
    track: Track
    analysis: Analysis


def effective_bpm(bpm: float, target: float) -> float:
    """Treat half- and double-time readings as the same groove."""
    options = [bpm, bpm * 2, bpm / 2]
    return min(options, key=lambda b: abs(b - target))


def energy_target(position: float) -> float:
    """Wanted relative energy at a point (0-1) through the mix."""
    if position < 0.2:
        return 0.55 + 0.45 * position / 0.2
    if position > 0.85:
        return 1.0 - 0.4 * (position - 0.85) / 0.15
    return 1.0


def plan_mix(candidates: list[Candidate], req: PlanRequest) -> Plan:
    pool = [c for c in candidates if _usable(c, req)]
    if not pool:
        raise PlanError("no analysed tracks match that request")
    rng = random.Random(req.seed)

    # The groove: the tempo most of the pool sits around (bpm range if asked).
    centre = median(c.analysis.bpm for c in pool)
    if req.bpm_min or req.bpm_max:
        lo, hi = req.bpm_min or 0, req.bpm_max or 1000
        centre = min(max(centre, lo), hi)
    pool = [
        c
        for c in pool
        if abs(effective_bpm(c.analysis.bpm, centre) / centre - 1) <= MAX_STRETCH * 1.5
    ]
    if not pool:
        raise PlanError("no tracks near a common tempo")

    max_energy = max(c.analysis.energy for c in pool) or 1.0
    chosen: list[Candidate] = []
    total = 0.0
    beat_s = 60.0 / centre

    def contribution(c: Candidate) -> float:
        return _segment_s(c, centre) - req.transition_beats * beat_s

    while total < req.duration_s and pool:
        position = total / req.duration_s
        want = energy_target(position)
        prev = chosen[-1] if chosen else None

        def score(c: Candidate, prev=prev, want=want) -> float:
            e = c.analysis.energy / max_energy
            s = -abs(e - want) * 1.5
            s -= abs(effective_bpm(c.analysis.bpm, centre) / centre - 1) * 10
            if prev:
                s += camelot.compatibility(prev.analysis.camelot, c.analysis.camelot) * 2
                if c.track.artist == prev.track.artist:
                    s -= 0.75
            return s + rng.random() * 0.6

        best = max(pool, key=score)
        pool.remove(best)
        chosen.append(best)
        total += contribution(best)

    if total < req.duration_s * 0.8:
        raise PlanError(
            f"only {total / 60:.0f} min of suitable music for {req.duration_s / 60:.0f} min"
        )

    tempo = median(effective_bpm(c.analysis.bpm, centre) for c in chosen)
    return _layout(chosen, tempo, req)


def _usable(c: Candidate, req: PlanRequest) -> bool:
    a, t = c.analysis, c.track
    if req.libraries and t.library not in req.libraries:
        return False
    if req.genres and not {g.lower() for g in t.genres} & {g.lower() for g in req.genres}:
        return False
    if a.bpm < 60 or a.bpm > 200 or len(a.downbeats) < 24:
        return False
    if a.grid_confidence < MIN_GRID_CONFIDENCE:
        return False
    return _segment_beats(c) >= MIN_SEGMENT_BEATS + req.transition_beats


def _segment_beats(c: Candidate) -> int:
    a = c.analysis
    return sum(1 for b in a.beats if a.mix_in_s <= b < a.mix_out_s)


def _segment_s(c: Candidate, tempo: float) -> float:
    a = c.analysis
    rate = tempo / effective_bpm(a.bpm, tempo)
    return (a.mix_out_s - a.mix_in_s) / rate


def _layout(chosen: list[Candidate], tempo: float, req: PlanRequest) -> Plan:
    items: list[PlanItem] = []
    t = 0.0
    beat_s = 60.0 / tempo
    for i, c in enumerate(chosen):
        a = c.analysis
        rate = tempo / effective_bpm(a.bpm, tempo)
        # Use the whole track at the edges of the mix: the opener's intro and
        # the closer's outro are welcome there.
        cue_in = a.downbeats[0] if i == 0 else a.mix_in_s
        cue_out = a.downbeats[-1] if i == len(chosen) - 1 else a.mix_out_s
        last = i == len(chosen) - 1
        items.append(
            PlanItem(
                track_id=c.track.id,
                title=c.track.title,
                artist=c.track.artist,
                library=c.track.library,
                bpm=a.bpm,
                camelot=a.camelot,
                rate=round(rate, 6),
                cue_in_s=cue_in,
                cue_out_s=cue_out,
                start_s=round(t, 3),
                transition_beats=0 if last else req.transition_beats,
            )
        )
        length = (cue_out - cue_in) / rate
        t += length - (0 if last else req.transition_beats * beat_s)
    return Plan(tempo_bpm=tempo, items=items, duration_s=t, genres=req.genres, seed=req.seed)
