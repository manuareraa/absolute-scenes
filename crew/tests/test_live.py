"""Posting verified overlays to the edge Worker, with an in-memory stand-in for it."""

import json

import pytest
from chalktalk_crew.live import SECRET_HEADER, OverlayPoster, PostError
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
