"""Posting verified overlays to the edge Worker, with an in-memory stand-in for it."""

import json

import pytest
from chalktalk_crew.live import (
    SECRET_HEADER,
    OverlayPoster,
    PostError,
    verified_overlays,
    watch,
    ws_clock,
)
from chalktalk_crew.pipeline import RunOptions, run

SECRET = "test-secret-not-real"


class Edge:
    """Answers like ``workers/edge`` /api/overlay: 403 without the secret, then {ok, id}."""

    def __init__(self, fail: list[int] | None = None) -> None:
        self.got: list[dict] = []
        self.fail = list(fail or [])

    def __call__(self, url, headers, body):
        assert url == "http://edge.invalid/api/overlay"
        if headers.get(SECRET_HEADER) != SECRET:
            return 403, "forbidden"
        if self.fail:
            return self.fail.pop(0), "busy"
        data = json.loads(body)
        self.got.append(data)
        return 200, json.dumps({"ok": True, "id": data["overlay"]["id"], "viewers": 0})


def poster(edge, secret=SECRET):
    return OverlayPoster("http://edge.invalid/", secret, post=edge)


def opts(tmp_path, max_moments=2):
    return RunOptions(seed=7, half_minutes=3.0, max_moments=max_moments, cache=tmp_path, post=True)


def test_pipeline_posts_fresh_then_cached_overlays(tmp_path):
    edge = Edge()
    log = run(opts(tmp_path), poster=poster(edge))
    assert log.generated and log.posted == log.generated and not log.post_failed
    assert {p["overlay"]["id"] for p in edge.got} == set(log.generated)
    assert all(p["match_id"] == log.match_id for p in edge.got)
    # cached overlays are replayed, not regenerated
    again = run(opts(tmp_path), poster=poster(edge))
    assert not again.generated and again.posted == log.generated


def test_without_post_nothing_is_sent(tmp_path):
    edge = Edge()
    log = run(
        RunOptions(seed=7, half_minutes=3.0, max_moments=1, cache=tmp_path), poster=poster(edge)
    )
    assert log.generated and not log.posted and not edge.got


def test_wrong_secret_is_logged_not_raised(tmp_path):
    log = run(opts(tmp_path), poster=poster(Edge(), secret="wrong"))
    assert log.generated and not log.posted
    assert all(v.startswith("HTTP 403") for v in log.post_failed.values())


def test_poster_retries_busy_edge_only(monkeypatch, tmp_path):
    monkeypatch.setattr("chalktalk_crew.live.time.sleep", lambda s: None)
    log = run(opts(tmp_path, max_moments=1), poster=poster(Edge(fail=[503, 429])))
    assert log.posted and not log.post_failed
    edge = Edge(fail=[400])
    with pytest.raises(PostError, match="HTTP 400"):
        poster(edge).send("m1", json.loads(next((tmp_path).rglob("overlays/*.json")).read_text()))


def test_unverified_overlays_are_never_posted():
    with pytest.raises(PostError, match="not verified"):
        poster(Edge()).send("m1", {"id": "x", "gate": {"passed": False}})


def test_from_env_needs_a_secret():
    with pytest.raises(RuntimeError, match="CHALKTALK_OVERLAY_SECRET"):
        OverlayPoster.from_env({})
    p = OverlayPoster.from_env({"CHALKTALK_OVERLAY_SECRET": SECRET})
    assert p.url == "http://127.0.0.1:8787/api/overlay" and SECRET not in repr(p)


def ov(i, tc, passed=True):
    return {"id": f"ov-{i}", "match_tc": tc, "gate": {"passed": passed}}


class Recorder:
    """Stands in for ``OverlayPoster``: records sends, fails ids listed in ``fail``."""

    def __init__(self, fail=()):
        self.sent, self.fail = [], set(fail)

    def send(self, match_id, overlay):
        if overlay["id"] in self.fail:
            raise PostError("HTTP 500: busy")
        self.sent.append(overlay["id"])


def test_watch_posts_each_overlay_ahead_of_its_moment():
    rec = Recorder()
    clock = iter(range(0, 60_000, 1000))
    log = watch(clock, [ov(2, 30_000), ov(1, 12_000)], rec, "sim-7", ahead_ms=8000)
    assert rec.sent == ["ov-1", "ov-2"]
    assert log.posted == {"ov-1": 4000, "ov-2": 22_000}
    assert log.last_t == 22_000  # stops once everything is posted


def test_watch_skips_aired_moments_and_logs_failures():
    rec = Recorder(fail={"ov-3"})
    log = watch(
        iter([20_000, 21_000, 40_000]),
        [ov(1, 5000), ov(2, 21_000), ov(3, 25_000)],
        rec,
        "sim-7",
        ahead_ms=8000,
    )
    assert log.missed == ["ov-1"] and rec.sent == ["ov-2"] and list(log.failed) == ["ov-3"]


def test_watch_ends_with_the_clock():
    log = watch(iter([0, 1000]), [ov(1, 50_000)], Recorder(), "sim-7")
    assert not log.posted and log.last_t == 1000


def test_ws_clock_reads_hello_frames_and_clock_until_end():
    import threading

    from websockets.sync.server import serve

    msgs = [
        {"type": "hello", "viewers": 1, "clock": {"t": 1000, "playing": True}},
        {"type": "frames", "t0": 1000, "t1": 2000, "clock": {"t": 2000}, "frames": []},
        {"type": "overlay", "overlay": {"id": "x"}},
        {"type": "clock", "clock": {"t": 9000, "playing": True}},
        {"type": "end", "clock": {"t": 600_000}},
    ]
    paths = []

    def handler(ws):
        paths.append(ws.request.path)
        for m in msgs:
            ws.send(json.dumps(m))
        ws.recv()  # hold until the client closes

    with serve(handler, "127.0.0.1", 0) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.socket.getsockname()[1]
        ticks = list(ws_clock(f"http://127.0.0.1:{port}", "sim-7", timeout_s=5))
        server.shutdown()
    assert ticks == [1000, 2000, 9000] and paths == ["/ws/match/sim-7"]


def test_verified_overlays_reads_fresh_and_cached(tmp_path):
    log = run(RunOptions(seed=7, half_minutes=3.0, max_moments=2, cache=tmp_path))
    got = verified_overlays(tmp_path, log)
    assert [o["id"] for o in got] == log.generated and all(o["gate"]["passed"] for o in got)
