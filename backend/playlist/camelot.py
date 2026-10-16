"""Musical keys on the Camelot wheel, and how well two keys mix.

Camelot numbers 1-12 go round the circle of fifths; A is minor, B is major.
Neighbours (same number, or one step either way with the same letter) mix
cleanly, which is the whole basis of harmonic mixing.
"""

from __future__ import annotations

PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Camelot number for each pitch class, major (B) and minor (A).
_MAJOR = {0: 8, 7: 9, 2: 10, 9: 11, 4: 12, 11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7}
_MINOR = {9: 8, 4: 9, 11: 10, 6: 11, 1: 12, 8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7}


def to_camelot(pitch_class: int, minor: bool) -> str:
    table = _MINOR if minor else _MAJOR
    return f"{table[pitch_class % 12]}{'A' if minor else 'B'}"


def key_name(pitch_class: int, minor: bool) -> str:
    return f"{PITCHES[pitch_class % 12]}{'m' if minor else ''}"


def parse(code: str) -> tuple[int, str]:
    code = code.strip().upper()
    num, letter = int(code[:-1]), code[-1]
    if not 1 <= num <= 12 or letter not in "AB":
        raise ValueError(f"not a Camelot code: {code!r}")
    return num, letter


def compatibility(a: str | None, b: str | None) -> float:
    """1.0 for a perfect harmonic match, falling towards 0 for a clash.

    Unknown keys score a neutral 0.5 so they are neither favoured nor shunned.
    """
    if not a or not b:
        return 0.5
    (na, la), (nb, lb) = parse(a), parse(b)
    step = min((na - nb) % 12, (nb - na) % 12)
    if step == 0:
        return 1.0 if la == lb else 0.85  # same key, or its relative major/minor
    if step == 1 and la == lb:
        return 0.9  # a fifth up or down
    if step == 2 and la == lb:
        return 0.55  # two steps: an energy boost, usable sparingly
    if step == 1:
        return 0.45  # diagonal move
    return max(0.0, 0.3 - 0.05 * step)
