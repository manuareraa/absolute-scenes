"""voice-show: crew chapters get their cached MP3, tool chapters are voiced once and retimed."""

import json
from dataclasses import replace

from chalktalk_crew import FakeSpeechClient
from chalktalk_crew.voice import cue_word_gap_ms, resnap_trailing, voice_show

SSML = (
    "<speak><voice name='en-GB-RyanNeural'>Look <bookmark mark='c1'/>here, then there.</voice>"
    "</speak>"
)


class Mp3Speech(FakeSpeechClient):
    def __init__(self) -> None:
        super().__init__(start_ms=300)
        self.characters = 0
        self.calls = 0

    def synthesize(self, ssml):
        self.calls += 1
        self.characters += len(ssml)
        return replace(super().synthesize(ssml), audio=b"ID3" + ssml.encode())


def overlay(oid, audio_url=None):
    script = {
        "text": "Look here, then there.",
        "ssml": SSML,
        # crew chapters are already timed by real speech; tool chapters by the fake estimate
        "cues": [{"cue_id": "c1", "offset_ms": 0 if audio_url else 9999}],
        "words": [{"text": "Look", "offset_ms": 0, "duration_ms": 100}],
    }
    if audio_url:
        script["audio_url"] = audio_url
    return {"id": oid, "script": script}


def fixture():
    shows = []
    for side in ("home", "away"):
        segs = [
            {
                "overlay": overlay(
                    f"ov-m1-casual-{side}-en-GB", f"audio/ov-m1-casual-{side}-en-GB.mp3"
                )
            },
            {"overlay": overlay(f"ov-ghost-{side}")},
        ]
        shows.append({"id": side, "segments": segs})
    return {"match_id": "sim-7", "shows": shows}


def test_voice_show_copies_crew_audio_and_voices_tool_chapters(tmp_path):
    root = tmp_path / "sim-7-abcd1234"
    (root / "audio").mkdir(parents=True)
    for side in ("home", "away"):
        (root / "audio" / f"ov-m1-casual-{side}-en-GB.mp3").write_bytes(b"ID3crew")
    out = tmp_path / "show-sim-7" / "audio"
    fx, speech = fixture(), Mp3Speech()

    log = voice_show(fx, root, out, speech)

    assert sorted(log.copied) == ["ov-m1-casual-away-en-GB", "ov-m1-casual-home-en-GB"]
    assert log.synthesized == ["ov-ghost-home"]  # same SSML: voiced once
    assert log.reused == ["ov-ghost-away"]
    assert speech.calls == 1 and log.speech_characters == len(SSML)
    ghost = fx["shows"][1]["segments"][1]["overlay"]
    assert ghost["script"]["audio_url"] == "audio/ov-ghost-home.mp3"
    assert ghost["script"]["cues"][0]["offset_ms"] != 9999
    assert ghost["script"]["words"][0]["offset_ms"] == 300
    assert cue_word_gap_ms(ghost) == 0  # the cue sits on the start of "here"
    assert log.cue_word_gap_max_ms == 0
    for seg in (s for show in fx["shows"] for s in show["segments"]):
        url = seg["overlay"]["script"]["audio_url"]
        assert (out.parent / url).exists()
    assert log.files == 3 and log.total_bytes == sum(f.stat().st_size for f in out.iterdir())

    again = Mp3Speech()  # a re-run is served from <root>/voiced and costs nothing
    log2 = voice_show(fixture(), root, out, again)
    assert again.calls == 0 and log2.speech_characters == 0 and log2.synthesized == []


def test_crew_chapter_without_cached_mp3_drops_its_url(tmp_path):
    fx = fixture()
    log = voice_show(fx, tmp_path / "root", tmp_path / "audio", Mp3Speech())
    assert len(log.missing) == 2
    assert "audio_url" not in fx["shows"][0]["segments"][0]["overlay"]["script"]


def test_no_audio_from_fake_speech_leaves_no_url(tmp_path):
    fx = fixture()
    voice_show(fx, tmp_path / "root", tmp_path / "audio", FakeSpeechClient())
    assert "audio_url" not in fx["shows"][0]["segments"][1]["overlay"]["script"]
    json.dumps(fx)


def test_resnap_moves_a_cue_written_after_its_word_back_onto_it():
    # Cached before snap_bookmarks learned this: the trailing cue sat at the end of the audio,
    # the mid-text one on the first word of the next clause.
    ov = {
        "id": "ov",
        "script": {
            "ssml": "<speak><voice>Un espacio <bookmark mark='k1'/>. Esas ocasiones, "
            "y ocasiones <bookmark mark='k2'/>.</voice></speak>",
            "cues": [{"cue_id": "k1", "offset_ms": 900}, {"cue_id": "k2", "offset_ms": 3100}],
            "words": [
                {"text": t, "offset_ms": o, "duration_ms": 100}
                for t, o in [("Un", 0), ("espacio", 200), ("Esas", 900), ("ocasiones", 1200),
                             ("y", 2000), ("ocasiones", 2300)]
            ],
        },
    }  # fmt: skip
    assert resnap_trailing(ov) == 2
    assert [c["offset_ms"] for c in ov["script"]["cues"]] == [200, 2300]
    assert resnap_trailing(ov) == 0  # idempotent
