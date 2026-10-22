import numpy as np
import pytest
from chalktalk_sim.director import MatchConfig, simulate
from chalktalk_vision.calib import LineCalibrator, template_points
from chalktalk_vision.camera import image_to_pitch
from chalktalk_vision.kits import KIT_KEYS, classify, shirt_colour, vote
from chalktalk_vision.mot import FrameData, box_iou, clear_and_id, hota, pitch_similarity
from chalktalk_vision.render import ClipSpec, Renderer, kit_key


@pytest.fixture(scope="module")
def frame():
    match = simulate(MatchConfig(seed=3, half_minutes=1.0))
    spec = ClipSpec(start_ms=20_000, seconds=0.04)
    return next(iter(Renderer(match, spec).frames())), spec


def _frames(gt_tracks, tr_tracks):
    """Build FrameData from {id: [box per frame or None]} for gt and tracker."""
    n = len(next(iter(gt_tracks.values())))
    out = []
    for k in range(n):
        g = {i: b[k] for i, b in gt_tracks.items() if b[k] is not None}
        t = {i: b[k] for i, b in tr_tracks.items() if b[k] is not None}
        sim = box_iou(list(g.values()), list(t.values()))
        out.append(FrameData(np.array(list(g), int), np.array(list(t), int), sim))
    return out


BOX_A = [0, 0, 10, 20]
BOX_B = [50, 0, 60, 20]


def test_perfect_tracker_scores_one():
    gt = {1: [BOX_A] * 5, 2: [BOX_B] * 5}
    fr = _frames(gt, {7: [BOX_A] * 5, 9: [BOX_B] * 5})
    h = hota(fr)
    c = clear_and_id(fr)
    assert h["HOTA"] == pytest.approx(1.0)
    assert c["MOTA"] == pytest.approx(1.0)
    assert c["IDF1"] == pytest.approx(1.0)


def test_id_swap_hurts_association_not_detection():
    gt = {1: [BOX_A] * 4, 2: [BOX_B] * 4}
    tr = {7: [BOX_A, BOX_A, BOX_B, BOX_B], 9: [BOX_B, BOX_B, BOX_A, BOX_A]}
    fr = _frames(gt, tr)
    h = hota(fr)
    c = clear_and_id(fr)
    assert h["DetA"] == pytest.approx(1.0)
    assert h["AssA"] == pytest.approx(1 / 3)
    assert c["IDSW"] == 2
    assert c["MOTA"] == pytest.approx(1 - 2 / 8)
    assert c["IDF1"] == pytest.approx(0.5)


def test_missing_tracker_scores_zero():
    gt = {1: [BOX_A] * 3}
    fr = _frames(gt, {5: [None] * 3})
    assert hota(fr)["HOTA"] == 0
    assert clear_and_id(fr)["MOTA"] == 0


def test_pitch_similarity_scale():
    s = pitch_similarity([[0, 0]], [[0, 0], [5, 0], [0, 50]])
    assert s[0] == pytest.approx([1.0, 0.05, 0.0], abs=1e-6)


def test_line_calibration_recovers_the_camera(frame):
    fr, spec = frame
    boxes = np.array([p["bbox"] for p in fr.truth["players"] if p["bbox"]])
    cal = LineCalibrator(spec.camera_pos, spec.width, spec.height)
    ptz, cost = cal.fit(fr.image, boxes)
    assert cost < 5
    H_fit = ptz.camera(spec.camera_pos, spec.width, spec.height).ground_homography()
    H_gt = np.array(fr.truth["H"])
    errs = []
    for p in fr.truth["players"]:
        if p["bbox"] and p["visible"] > 0.9:
            q = H_gt @ [p["x"], p["y"], 1]
            xy = image_to_pitch(H_fit, q[:2] / q[2])[0]
            errs.append(np.hypot(xy[0] - p["x"], xy[1] - p["y"]))
    assert len(errs) > 5
    assert np.median(errs) < 0.5
    assert len(template_points()) > 500


def test_kits_classify_their_own_colours_and_rendered_shirts(frame):
    from chalktalk_vision.render import _HEX, _bgr

    for key in KIT_KEYS:
        got, conf = classify(np.array(_bgr(_HEX[key][0]), float))
        assert got == key and conf > 0.3
    fr, _ = frame
    right = total = 0
    for p in fr.truth["players"]:
        if p["bbox"] and p["visible"] > 0.9:
            got, _ = classify(shirt_colour(fr.image, p["bbox"]))
            total += 1
            right += got == kit_key(p["team"], p["role"])
    assert total > 5 and right / total > 0.9
    assert vote(["home", "home", None, "away"]) == ("home", pytest.approx(2 / 3))
