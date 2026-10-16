from __future__ import annotations

import numpy as np
import pytest

from playlist import camelot, manifest, planner
from playlist.cache import Cache
from playlist.config import Settings
from playlist.jobs import _safe
from playlist.library import LicenceIndex, _folder_genre
from playlist.planner import Candidate, PlanError, PlanRequest

from .conftest import fake_analysis, fake_track


def test_camelot_table():
    assert camelot.to_camelot(0, minor=False) == "8B"  # C major
    assert camelot.to_camelot(9, minor=True) == "8A"  # A minor
    assert camelot.to_camelot(7, minor=False) == "9B"  # G major
    assert camelot.key_name(1, True) == "C#m"


def test_camelot_compatibility_ordering():
    same, fifth, relative = (camelot.compatibility("8A", x) for x in ("8A", "9A", "8B"))
    far = camelot.compatibility("8A", "2B")
    assert same > fifth > relative > far
    assert camelot.compatibility("12A", "1A") == pytest.approx(0.9)  # wraps round
    assert camelot.compatibility(None, "8A") == 0.5
    with pytest.raises(ValueError):
        camelot.parse("13A")


def test_settings_from_env_and_path_map():
    s = Settings.from_env(
        {
            "PLAYLIST_PATH_MAP": "/data=/mnt/nas, /x=/y",
            "PLAYLIST_LIBRARIES": "Music,Purchased",
            "PLEX_TOKEN": "t",
        }
    )
    assert str(s.local_path("/data/music/a.mp3")) == "/mnt/nas/music/a.mp3"
    assert str(s.local_path("/database/a.mp3")) == "/database/a.mp3"  # prefix, not substring
    assert s.is_cc("Music") and not s.is_cc("Purchased")


def test_effective_bpm_handles_half_and_double_time():
    assert planner.effective_bpm(70, 140) == 140
    assert planner.effective_bpm(260, 130) == 130
    assert planner.effective_bpm(128, 130) == 128


def test_energy_curve_shape():
    assert planner.energy_target(0.0) < planner.energy_target(0.5)
    assert planner.energy_target(0.99) < planner.energy_target(0.5)


def _cands(n=12, bpm=128.0, seconds=300, **kw):
    keys = ["8A", "9A", "8B", "10A", "7A", "9B"]
    return [
        Candidate(
            fake_track(i, **kw),
            fake_analysis(
                bpm + (i % 3) * 0.5, seconds, keys[i % len(keys)], energy=0.5 + (i % 4) * 0.1
            ),
        )
        for i in range(n)
    ]


def test_plan_fits_duration_and_is_deterministic():
    req = PlanRequest(duration_s=20 * 60, genres=["trance"], seed=42)
    a = planner.plan_mix(_cands(), req)
    b = planner.plan_mix(_cands(), req)
    assert [i.track_id for i in a.items] == [i.track_id for i in b.items]
    assert a.duration_s >= 20 * 60 * 0.8
    assert len({i.track_id for i in a.items}) == len(a.items)  # no repeats
    assert all(abs(i.rate - 1) <= planner.MAX_STRETCH for i in a.items)
    assert a.items[-1].transition_beats == 0
    starts = [i.start_s for i in a.items]
    assert starts == sorted(starts)


def test_plan_reroll_differs():
    req = PlanRequest(duration_s=15 * 60)
    orders = {
        tuple(
            i.track_id
            for i in planner.plan_mix(
                _cands(), PlanRequest(duration_s=req.duration_s, seed=s)
            ).items
        )
        for s in range(6)
    }
    assert len(orders) > 1


def test_plan_filters_and_errors():
    with pytest.raises(PlanError):
        planner.plan_mix(_cands(), PlanRequest(duration_s=600, genres=["polka"]))
    with pytest.raises(PlanError):
        planner.plan_mix(_cands(n=2), PlanRequest(duration_s=60 * 60))
    weak = [Candidate(c.track, fake_analysis(128, 300, confidence=0.1)) for c in _cands()]
    with pytest.raises(PlanError):
        planner.plan_mix(weak, PlanRequest(duration_s=600))


def test_manifest_publishable_only_when_all_cc():
    cands = _cands(n=6)
    plan = planner.plan_mix(cands, PlanRequest(duration_s=10 * 60))
    tracks = {c.track.id: c.track for c in cands}
    m = manifest.build_manifest(plan, tracks, ("Music",))
    assert m["publishable"] is True
    assert "CC BY 4.0" in m["attribution_text"]

    first = plan.items[0].track_id
    tracks[first] = fake_track(int(first[1:]), library="Purchased")
    m = manifest.build_manifest(plan, tracks, ("Music",))
    assert m["publishable"] is False
    assert m["attribution_text"] == ""
    assert any(r["licence"] == manifest.PURCHASED_LICENCE for r in m["tracks"])


def test_cache_roundtrip(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    tracks = [fake_track(i, genres=("Trance", "Dance")) for i in range(3)]
    tracks.append(fake_track(9, library="Purchased", genres=("Pop",)))
    assert c.upsert_tracks(tracks) == 4
    assert {t.id for t in c.tracks(["Music"])} == {"t0", "t1", "t2"}
    assert c.genres(["Music"])[0] == ("Dance", 3)
    a = fake_analysis(128, 200)
    c.save_analysis("t0", a)
    c.save_error("t1", "boom", a.version)
    assert c.analysis("t0").bpm == 128
    assert c.analysis("t1") is None
    assert {t.id for t in c.pending(a.version, ["Music"])} == {"t2"}
    assert c.stats()["Music"] == {"tracks": 3, "analysed": 1, "failed": 1}
    assert c.remove_missing("Music", {"t0"}) == 2
    assert c.track("t1") is None


def test_licence_index_and_folder_genre(tmp_path):
    lib = tmp_path / "cc-ambient"
    (lib / "A").mkdir(parents=True)
    (lib / "tracks.json").write_text(
        '[{"file": "A/a.mp3", "licence": "CC0 1.0", "source_url": "u"}]'
    )
    idx = LicenceIndex()
    assert idx.lookup(str(lib / "A" / "a.mp3"))["licence"] == "CC0 1.0"
    assert idx.lookup(str(lib / "A" / "b.mp3")) == {}
    assert _folder_genre("/data/music/cc-ambient/A/a.mp3") == ["Ambient"]
    assert _folder_genre("/data/purchased/x.mp3") == []


def test_safe_titles_are_fat_friendly():
    assert _safe('a/b:c*?"<>|') == "a-b-c------"
    assert _safe("  ...  ") == "mix"


def test_fit_grid_recovers_tempo_from_jittery_beats():
    from playlist.analysis import fit_grid

    rng = np.random.default_rng(0)
    true_period = 60 / 128.0
    beats = np.arange(400) * true_period + 0.2
    beats = beats + rng.uniform(-0.011, 0.011, len(beats))  # frame quantisation
    beats = np.delete(beats, [50, 51, 200])  # missed beats
    grid, bpm = fit_grid(beats, 60 / 129.2, 400 * true_period)
    assert bpm == pytest.approx(128.0, abs=0.02)
    assert abs(grid[0] - 0.2) < 0.005


def test_sync_plex_inherits_genres_and_licences(tmp_path):
    import httpx

    from playlist.library import PlexClient, sync_plex

    lib = tmp_path / "nas" / "music" / "cc-ambient"
    (lib / "A").mkdir(parents=True)
    (lib / "tracks.json").write_text(
        '[{"file": "A/one.mp3", "licence": "CC BY 4.0", "source_url": "https://fma/1"}]'
    )
    data = {
        "/library/sections": {
            "Directory": [
                {"key": "1", "title": "Music", "type": "artist"},
                {"key": "2", "title": "Purchased", "type": "artist"},
                {"key": "3", "title": "Films", "type": "movie"},
                {"key": "4", "title": "Audiobooks", "type": "artist"},
            ]
        },
        ("1", "8"): {"Metadata": [{"ratingKey": "a1", "Genre": [{"tag": "Ambient"}]}]},
        ("1", "9"): {"Metadata": [{"ratingKey": "al1"}]},
        ("1", "10"): {
            "Metadata": [
                {
                    "ratingKey": "100",
                    "title": "One",
                    "grandparentTitle": "A",
                    "parentRatingKey": "al1",
                    "grandparentRatingKey": "a1",
                    "duration": 200000,
                    "Media": [{"Part": [{"file": "/data/music/cc-ambient/A/one.mp3"}]}],
                },
                {"ratingKey": "101", "title": "No media"},
            ]
        },
        ("2", "8"): {"Metadata": []},
        ("2", "9"): {"Metadata": [{"ratingKey": "al2", "Genre": [{"tag": "Trance"}]}]},
        ("2", "10"): {
            "Metadata": [
                {
                    "ratingKey": "200",
                    "title": "Two",
                    "originalTitle": "Guest",
                    "grandparentTitle": "B",
                    "parentRatingKey": "al2",
                    "Media": [{"Part": [{"file": "/data/purchased/B/two.mp3"}]}],
                }
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Plex-Token"] == "tok"
        path = request.url.path
        if path == "/library/sections":
            body = data[path]
        else:
            body = data[(path.split("/")[3], request.url.params["type"])]
        return httpx.Response(200, json={"MediaContainer": body})

    settings = Settings(plex_token="tok", path_map=(("/data", str(tmp_path / "nas")),))
    cache = Cache(":memory:")
    client = httpx.Client(base_url="http://plex", transport=httpx.MockTransport(handler))
    counts = sync_plex(settings, cache, PlexClient("http://plex", "tok", client))
    assert counts == {"Music": 1, "Purchased": 1}
    one, two = cache.track("100"), cache.track("200")
    assert one.genres == ["Ambient"]  # from the artist
    assert one.licence == "CC BY 4.0" and one.source_url == "https://fma/1"
    assert one.path == str(lib / "A" / "one.mp3")
    assert one.duration_s == 200
    assert two.genres == ["Trance"] and two.artist == "Guest" and two.licence == ""
