import json

from chalktalk_contracts import validate
from chalktalk_sim import write_package
from chalktalk_sim.__main__ import main
from chalktalk_sim.package import read_chunk
from chalktalk_sim.realism import compare, ks_from_quantiles, profile


def test_package_roundtrip(match, tmp_path):
    root = write_package(match, tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["match_id"] == "sim-11"
    assert sum(c["frames"] for c in manifest["chunks"]) == match.n_frames
    assert manifest["chunks"][1]["start_t"] == 10_000
    first = read_chunk(root, manifest["chunks"][0]["file"])
    assert len(first) == 250
    validate("frame", first[-1])
    assert first[3] == match.frame(3)
    events = json.loads((root / "events.json").read_text())
    assert len(events) == manifest["events"]["count"]
    names = {p["name"] for t in manifest["teams"].values() for p in t["players"]}
    assert len(names) == 22


def test_package_bytes_are_deterministic(match, tmp_path):
    a = write_package(match, tmp_path / "a")
    b = write_package(match, tmp_path / "b")
    f = "chunks/c00002.json.gz"
    assert (a / f).read_bytes() == (b / f).read_bytes()


def test_ks():
    q = [float(i) for i in range(101)]
    assert ks_from_quantiles(q, q) == 0.0
    shifted = [v + 50 for v in q]
    assert 0.45 < ks_from_quantiles(q, shifted) < 0.55


def test_profile_and_self_compare(match):
    prof = profile(match)
    assert {"speed_ms", "accel_ms2", "pass_length_m", "pressure_distance_m"} <= set(prof)
    assert 0.5 < prof["speed_ms"]["q"][50] < 4.0
    report = compare(prof, prof)
    assert all(r["ks"] == 0.0 for r in report.values())


def test_cli_generate(tmp_path, capsys):
    assert main(["generate", "--seed", "2", "--half-minutes", "0.2", "--out", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (tmp_path / "sim-2" / "manifest.json").exists()
    assert set(out["score"]) == {"home", "away"}
