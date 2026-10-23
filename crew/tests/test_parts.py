import pytest
from chalktalk_crew import Director, FakeAnalyticsTools, FakeSpeechClient
from chalktalk_crew.llm import SYSTEM_PROMPT, Beat, DraftRequest, render_prompt
from chalktalk_crew.script import TemplateError, check_template, format_value, render
from chalktalk_crew.tools import call_tools, output_hash
from crew_events import counter_then_foul, ev


def test_director_finds_stoppage_and_attacking_team():
    (m,) = Director().moments(counter_then_foul())
    assert m.trigger == "foul" and m.attacking == "home" and m.defending == "away"
    assert m.focus_t == 605_000 and m.focus_player == "a6"
    assert m.window == (593_600, 605_600)


def test_director_dedupes_close_stoppages_and_skips_empty_play():
    events = [
        ev(1, 10_000, "pass", "home", ["h2"]),
        ev(2, 11_000, "ball_out"),
        ev(3, 15_000, "throw_in", "away", ["a2"]),
        ev(4, 200_000, "goal_kick"),  # no play in the lookback window
    ]
    moments = Director().moments(events)
    assert [m.t for m in moments] == [11_000]


def test_fake_tools_are_deterministic_and_on_pitch():
    tools = FakeAnalyticsTools()
    for name in FakeAnalyticsTools.NAMES:
        a = tools.call(name, {"t": 1, "team": "home"})
        assert a == tools.call(name, {"t": 1, "team": "home"})
        assert a["provenance"]["impl"] == "fake"
        for x, y in a["geometry"].get("points", []):
            assert -52.5 <= x <= 52.5 and -34 <= y <= 34
    with pytest.raises(KeyError):
        tools.call("nope", {})


def test_call_tools_keeps_order_and_hashes():
    res = call_tools(FakeAnalyticsTools(), [("xg", {"t": 1}), ("line_gap", {"t": 1})])
    assert [r.name for r in res] == ["xg", "line_gap"]
    assert [r.id for r in res] == ["tc1", "tc2"]
    assert res[0].output_hash == output_hash(res[0].output)
    assert res[0].tool_call["output_hash"].startswith("sha256:")


def test_format_value():
    assert format_value(12.0, "m") == "12.0"
    assert format_value(0.3, "xG") == "0.30"
    assert format_value(73.6, "%") == "74"
    assert format_value(3, "players") == "3"
    assert format_value("high", None) == "high"


@pytest.mark.parametrize(
    "template",
    [
        "The gap is 12 metres [[k1]]here.",  # free digit
        "The [[k1]]gap is {nope}.",  # unknown slot
        "The gap is {gap_m}.",  # missing cue
        "The [[k1]]gap [[k1]]is {gap_m}.",  # duplicate cue
    ],
)
def test_check_template_rejects(template):
    with pytest.raises(TemplateError):
        check_template(template, {"gap_m"}, {"k1"})


def test_render_escapes_and_bookmarks():
    r = render("Look at [[k1]]Tom & Jo's {gap_m} <gap>.", {"gap_m": "9.5"}, lang="en-GB", voice="v")
    assert r.text == "Look at Tom & Jo's 9.5 <gap>."
    assert "<bookmark mark='k1'/>Tom &amp; Jo's 9.5 &lt;gap&gt;." in r.ssml
    assert r.cue_order == ["k1"]


def test_fake_speech_bookmarks_land_on_next_word():
    ssml = (
        "<speak><voice name='v'>One, <bookmark mark='a'/>two &amp; three"
        "<bookmark mark='z'/></voice></speak>"
    )
    res = FakeSpeechClient().synthesize(ssml)
    words = {w.text: w.offset_ms for w in res.words}
    assert res.bookmarks["a"] == words["two"]
    assert res.bookmarks["z"] == res.duration_ms
    assert [w.text for w in res.words] == ["One", "two", "&", "three"]


def test_prompt_prefix_is_stable():
    req = DraftRequest("casual", "home", "en-GB", "foul", [Beat("xg", "xg", "k1", "xG", "our")])
    msgs = render_prompt(req)
    assert msgs[0]["content"] == SYSTEM_PROMPT
    assert '"slot":"xg"' in msgs[1]["content"]


def test_check_template_wants_spanish_drawn_nouns():
    with pytest.raises(TemplateError, match="Spanish"):
        check_template("El [[k1]]gap es de {gap_m} metros.", {"gap_m"}, {"k1"}, lang="es-ES")
    check_template("El [[k1]]hueco es de {gap_m} metros.", {"gap_m"}, {"k1"}, lang="es-ES")
    check_template("The [[k1]]gap is {gap_m} metres.", {"gap_m"}, {"k1"}, lang="en-GB")


@pytest.mark.parametrize(
    ("template", "lang"),
    [
        ("A high [[k1]]chance, {xg} expected goals.", "en-GB"),
        ("Un [[k1]]disparo peligroso de {xg} goles esperados.", "es-ES"),
        ("Their [[k1]]shot was worth {xg} xG, showing how threatening it was.", "en-GB"),
    ],
)
def test_check_template_rejects_rated_xg(template, lang):
    with pytest.raises(TemplateError, match="rate the chance"):
        check_template(template, {"xg"}, {"k1"}, lang=lang, xg_slot="xg")


def test_rating_words_elsewhere_are_fine():
    template = "A big [[k1]]gap, {gap_m} metres. The [[k2]]shot carried {xg} xG."
    check_template(template, {"gap_m", "xg"}, {"k1", "k2"}, xg_slot="xg")
