"""Tests that run real audio through ffmpeg: analysis, rendering, jobs, API."""

from __future__ import annotations

import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from playlist import analysis, renderer
from playlist.api import create_app
from playlist.cache import Cache
from playlist.config import Settings
from playlist.jobs import JobManager, MixRequest
from playlist.library import analyse_pending, scan_folder

from .conftest import SR, click_track, have_ffmpeg

pytestmark = pytest.mark.skipif(not have_ffmpeg(), reason="needs ffmpeg")


def test_analysis_finds_tempo_and_kick(make_mp3):
    path = make_mp3("a", 128.0, 60, offset=0.3)
    a = analysis.analyse_file(str(path))
    assert a.bpm == pytest.approx(128.0, abs=0.1)
    assert a.grid_confidence >= analysis.KICK_SHARPNESS
    period = 60 / 128.0
    # Beats sit on the kicks (MP3 encoder delay allowed for).
    assert min(abs((a.beats[0] - 0.3) % period), period - (a.beats[0] - 0.3) % period) < 0.03
    assert a.mix_in_s < a.mix_out_s
    assert a.camelot


def test_analysis_rejects_short_audio():
    with pytest.raises(ValueError):
        analysis.analyse_signal(np.zeros(SR // 2 * 5, dtype=np.float32), SR // 2)


def test_choose_cuts():
    seg = 300 * SR
    cands = [i * SR * 2 for i in range(1, 600)]  # a bar start every 2 s for 20 min
    cuts = renderer.choose_cuts(cands, 1200 * SR, seg)
    assert len(cuts) == 3
    assert all(abs(c - (k + 1) * seg) <= 2 * SR for k, c in enumerate(cuts))
    assert renderer.choose_cuts([], 1200 * SR, seg) == []
    # A short final piece is merged rather than left as a stub.
    assert renderer.choose_cuts(cands, 620 * SR, seg) == [300 * SR]


def test_bass_swap_keeps_length_and_switches_lows():
    out = np.stack([np.sin(np.linspace(0, 400, SR * 4))] * 2, axis=1).astype(np.float32)
    inc = np.zeros_like(out)
    mixed = renderer.bass_swap(out, inc)
    assert mixed.shape == out.shape
    q = len(out) // 8
    assert np.abs(mixed[:q]).mean() > 10 * np.abs(mixed[-q:]).mean()


def test_align_offset_finds_a_late_kick():
    beat = 60 / 128
    a = click_track(128, 20)
    b = click_track(128, 20, offset=0.1)
    delay, conf = renderer.align_offset(a, b, beat)
    assert conf > 0.3
    assert delay / SR == pytest.approx(-0.1, abs=0.01)


@pytest.fixture
def library(tmp_path, make_mp3):
    folder = tmp_path / "lib"
    folder.mkdir()
    for i, bpm in enumerate([126.0, 126.5, 127.0, 126.0, 127.5, 126.5]):
        src = make_mp3(f"t{i}", bpm, 150, pitch=200 + 30 * i)
        src.rename(folder / src.name)
    settings = Settings(data_dir=tmp_path / "data", segment_minutes=2.0, libraries=("Music",))
    cache = Cache(settings.db_path)
    assert scan_folder(folder, "Music", cache, genre="Trance") == 6
    assert analyse_pending(cache, workers=1)["analysed"] == 6
    return settings, cache


def test_mix_end_to_end_split_and_single(library):
    settings, cache = library
    jobs = JobManager(settings, cache)
    job = jobs.submit(MixRequest(genres=["Trance"], duration_min=6, libraries=["Music"], seed=1))
    jobs.process(job)
    assert job.status == "done", job.error
    assert len(job.files) >= 2
    assert all((jobs.mix_dir(job.id) / f["name"]).stat().st_size > 10_000 for f in job.files)
    assert job.manifest["publishable"] is False  # scanned files carry no licence

    single = jobs.submit(
        MixRequest(genres=["Trance"], duration_min=6, libraries=["Music"], output="single", seed=1)
    )
    jobs.process(single)
    assert single.status == "done" and len(single.files) == 1

    failed = jobs.submit(MixRequest(genres=["Polka"], duration_min=6, libraries=["Music"]))
    jobs.process(failed)
    assert failed.status == "failed" and "no analysed tracks" in failed.error

    reloaded = JobManager(settings, cache)
    assert reloaded.get(job.id).status == "done"
    with pytest.raises(ValueError):
        jobs.submit(MixRequest(genres=[], duration_min=6, libraries=["Nope"]))


def test_api(library):
    settings, cache = library
    jobs = JobManager(settings, cache)
    jobs.start()
    client = TestClient(create_app(settings, cache, jobs))
    assert client.get("/api/health").json()["ok"]
    libs = client.get("/api/libraries").json()
    assert libs[0]["kind"] == "cc" and libs[0]["analysed"] == 6
    assert client.get("/api/genres?libraries=Music").json() == [{"name": "Trance", "count": 6}]
    assert client.post("/api/mixes", json={"duration_min": 1}).status_code == 400

    r = client.post(
        "/api/mixes",
        json={"genres": ["Trance"], "duration_min": 6, "libraries": ["Music"], "seed": 2},
    )
    assert r.status_code == 201
    mix_id = r.json()["id"]
    for _ in range(240):
        mix = client.get(f"/api/mixes/{mix_id}").json()
        if mix["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert mix["status"] == "done", mix
    f = mix["files"][0]
    assert client.get(f["url"]).headers["content-type"] == "audio/mpeg"
    z = client.get(f"/api/mixes/{mix_id}/zip")
    assert z.headers["content-type"] == "application/zip"
    assert "attachment" in z.headers["content-disposition"]
    assert client.get(f"/api/mixes/{mix_id}/files/nope.mp3").status_code == 404
    assert client.get("/api/mixes/nope").status_code == 404
    assert client.get("/api/mixes").json()[0]["id"] == mix_id


def test_mcp_tools(library):
    import asyncio

    from playlist.mcp_server import create_mcp

    settings, cache = library
    jobs = JobManager(settings, cache)
    mcp = create_mcp(settings, cache, jobs)

    async def call(name, **args):
        # call_tool returns (content, structured) for typed results, or just
        # the content blocks for plain dicts; read the JSON either way.
        out = await mcp.call_tool(name, args)
        if isinstance(out, tuple):
            structured = out[1]
            return structured.get("result", structured)
        return json.loads(out[0].text)

    assert asyncio.run(call("list_genres"))[0]["name"] == "Trance"
    assert len(asyncio.run(call("find_tracks", genre="trance", bpm_min=120))) == 6
    plan = asyncio.run(call("preview_plan", duration_min=6, genres=["Trance"]))
    assert plan["tracks"]
    assert "error" in asyncio.run(call("preview_plan", duration_min=6, genres=["Polka"]))
    created = asyncio.run(call("create_mix", duration_min=6, genres=["Trance"]))
    assert asyncio.run(call("get_mix", mix_id=created["id"]))["status"] == "queued"
    assert asyncio.run(call("get_mix", mix_id="nope")) == {"error": "no such mix"}
