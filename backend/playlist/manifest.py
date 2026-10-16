"""Licence manifest: where every track came from, and may the mix be published?

A mix is publishable only when every track is from a CC library. Anything
with a purchased track is for private listening, full stop.
"""

from __future__ import annotations

from .models import Plan, Track

PURCHASED_LICENCE = "All rights reserved (purchased for personal use)"


def build_manifest(plan: Plan, tracks: dict[str, Track], cc_libraries: tuple[str, ...]) -> dict:
    rows = []
    for item in plan.items:
        t = tracks[item.track_id]
        cc = t.library in cc_libraries
        licence = t.licence or (
            "Creative Commons (licence not recorded)" if cc else PURCHASED_LICENCE
        )
        rows.append(
            {
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "library": t.library,
                "cc": cc,
                "licence": licence,
                "licence_url": t.licence_url,
                "source_url": t.source_url,
                "attribution": attribution(t) if cc else "",
            }
        )
    publishable = (
        bool(rows)
        and all(r["cc"] for r in rows)
        and all(r["licence"] and "not recorded" not in r["licence"] for r in rows)
    )
    return {
        "publishable": publishable,
        "tracks": rows,
        "attribution_text": attribution_text(rows) if publishable else "",
    }


def attribution(t: Track) -> str:
    parts = [f'"{t.title}" by {t.artist}']
    if t.licence:
        parts.append(f"licensed under {t.licence}")
    if t.source_url:
        parts.append(t.source_url)
    return ", ".join(parts)


def attribution_text(rows: list[dict]) -> str:
    lines = ["Music (all Creative Commons):"]
    lines += [f"- {r['attribution']}" for r in rows]
    return "\n".join(lines)
