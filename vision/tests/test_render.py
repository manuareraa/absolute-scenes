import numpy as np
import pytest
from chalktalk_sim.director import MatchConfig, simulate
from chalktalk_vision.camera import Camera, image_to_pitch
from chalktalk_vision.render import ClipSpec, Renderer, kit_key, pitch_lines


@pytest.fixture(scope="module")
def match():
    return simulate(MatchConfig(seed=3, half_minutes=1.0))


def small_spec(**kw):
    return ClipSpec(start_ms=20_000, seconds=0.4, width=320, height=180, **kw)


def test_camera_homography_matches_projection():
    cam = Camera(position=(0, -62, 22), target=(10, 3, 0), hfov_deg=27)
    pts = np.array([[0, 0, 0], [20, -10, 0], [-30, 25, 0]], float)
    uv, depth = cam.project(pts)
    assert (depth > 0).all()
    back = image_to_pitch(cam.ground_homography(), uv)
    assert np.allclose(back, pts[:, :2], atol=1e-6)
    # The aim point lands at the image centre.
    centre, _ = cam.project(np.array([[10, 3, 0]]))
    assert np.allclose(centre[0], [640, 360], atol=1e-6)


def test_render_is_deterministic_and_boxes_hold_the_feet(match):
    frames_a = list(Renderer(match, small_spec()).frames())
    frames_b = list(Renderer(match, small_spec()).frames())
    assert len(frames_a) == 10
    assert all(np.array_equal(a.image, b.image) for a, b in zip(frames_a, frames_b, strict=True))
    fr = frames_a[-1]
    assert fr.image.shape == (180, 320, 3)
    Hm = np.array(fr.truth["H"])
    seen = 0
    for p in fr.truth["players"]:
        if not p["bbox"] or p["visible"] < 1:
            continue
        seen += 1
        x0, y0, x1, y1 = p["bbox"]
        foot = Hm @ [p["x"], p["y"], 1]
        u, v = foot[:2] / foot[2]
        assert x0 <= u <= x1 and y0 <= v <= y1 + 1e-6
    assert seen >= 3


def test_truth_lists_everyone_with_kits(match):
    fr = next(Renderer(match, small_spec()).frames())
    ids = [p["id"] for p in fr.truth["players"]]
    assert ids == [p.id for p in match.lineup]
    assert fr.truth["t"] == 20_000
    assert kit_key("home", "GK") == "home_gk" and kit_key("ref", "REF") == "ref"


def test_pitch_lines_stay_on_the_pitch():
    pts = np.concatenate(pitch_lines())
    assert np.abs(pts[:, 0]).max() <= 52.5 + 1e-9
    assert np.abs(pts[:, 1]).max() <= 34 + 1e-9
