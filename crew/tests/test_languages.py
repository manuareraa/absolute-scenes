"""Two languages: each with its own script, voice, bookmarks, spoken numbers and captions."""

import json
import re

import pytest
from chalktalk_contracts import validate
from chalktalk_crew import LENSES, SIDES, CrewConfig, FakeLLMClient, fake_crew
from chalktalk_crew.azure import AzureSpeechClient
from chalktalk_crew.captions import phrases, webvtt
from chalktalk_crew.lang import LANGS, UnsupportedLanguage, get_lang, team_ref, voice_for
from chalktalk_crew.llm import PHRASES_BY_LANG
from chalktalk_crew.pipeline import RunOptions, run
from chalktalk_crew.script import NUMBER, check_template, format_value
from crew_events import ALL

LANG_CODES = tuple(LANGS)


@pytest.fixture(scope="module")
def by_lang():
    crew = fake_crew()
    return {
        lang: [
            ov for f in ALL.values() for ov in crew.run(f(), lenses=LENSES, sides=SIDES, lang=lang)
        ]
        for lang in LANG_CODES
    }


def test_at_least_two_languages():
    assert {"en-GB", "es-ES"} <= set(LANGS)


@pytest.mark.parametrize("lang", LANG_CODES)
def test_every_overlay_passes_in_each_language(by_lang, lang):
    for ov in by_lang[lang]:
        validate("overlay", ov)
        assert ov["gate"]["passed"], (ov["id"], ov["gate"])
        assert ov["lang"] == lang and ov["id"].endswith(lang)
        assert ov["gate"]["scores"]["template_fallback"] == 0.0


@pytest.mark.parametrize("lang", LANG_CODES)
def test_ssml_carries_the_language_voice_and_one_bookmark_per_cue(by_lang, lang):
    voice = LANGS[lang].voice
    for ov in by_lang[lang]:
        ssml = ov["script"]["ssml"]
        assert f"xml:lang='{lang}'" in ssml and f"<voice name='{voice}'>" in ssml
        marks = re.findall(r"<bookmark mark='([^']+)'/>", ssml)
        assert marks == [c["cue_id"] for c in ov["script"]["cues"]]


def test_spanish_speaks_decimals_with_a_comma(by_lang):
    spoken = [n for ov in by_lang["es-ES"] for n in NUMBER.findall(ov["script"]["text"])]
    assert any("," in n for n in spoken) and not any("." in n for n in spoken)
    for ov in by_lang["es-ES"]:
        claimed = {format_value(c["value"], c["unit"], "es-ES") for c in ov["claims"]}
        assert set(NUMBER.findall(ov["script"]["text"])) <= claimed


def test_same_claims_and_strokes_in_every_language(by_lang):
    en, es = by_lang["en-GB"], by_lang["es-ES"]
    assert len(en) == len(es)
    for a, b in zip(en, es, strict=True):
        assert a["claims"] == b["claims"] and a["strokes"] == b["strokes"]
        assert a["script"]["text"] != b["script"]["text"]


def test_verifier_rejects_an_english_number_in_a_spanish_script(by_lang):
    crew = fake_crew()
    ov = next(o for o in by_lang["es-ES"] if "," in o["script"]["text"])
    n = next(n for n in NUMBER.findall(ov["script"]["text"]) if "," in n)
    bad = {
        **ov,
        "script": {**ov["script"], "text": ov["script"]["text"].replace(n, n.replace(",", "."))},
    }
    assert not crew.verifier.check(bad)["gate"]["passed"]


def test_number_formats():
    assert format_value(0.3, "xG", "es-ES") == "0,30"
    assert format_value(12.25, "m", "es") == "12,2"
    assert format_value(73.6, "%", "es-ES") == "74"
    assert format_value(0.3, "xG") == "0.30"


def test_team_refs_and_voices():
    assert team_ref("home", "home", "es-ES") == "nuestro equipo"
    assert team_ref("home", "away", "es-ES") == "el rival"
    assert team_ref("neutral", "away", "es-ES") == "el equipo visitante"
    assert team_ref("neutral", "home") == "the home side's"
    assert voice_for("es-ES", "en-GB-RyanNeural") == "es-ES-AlvaroNeural"
    assert voice_for("en-GB", "en-GB-SoniaNeural") == "en-GB-SoniaNeural"
    assert get_lang("es-MX") is LANGS["es-ES"]
    with pytest.raises(UnsupportedLanguage):
        get_lang("fr-FR")


def test_fake_phrases_cover_every_tool_and_lens_in_every_language():
    tools = set(PHRASES_BY_LANG["en"])
    for table in PHRASES_BY_LANG.values():
        assert set(table) == tools
        for lenses in table.values():
            assert set(lenses) == set(LENSES)
            for phrase in lenses.values():
                template = phrase.format(cue="k1", slot="v", team="x", Team="X")
                check_template(template, {"v"}, {"k1"})


def test_speech_client_takes_voice_and_locale_from_the_ssml():
    env = {"AZURE_SPEECH_REGION": "koreacentral", "AZURE_SPEECH_KEY": "test"}
    client = AzureSpeechClient(CrewConfig.from_env(env))
    ssml = (
        "<speak version='1.0' xml:lang='es-ES'><voice name='es-ES-AlvaroNeural'>Hola</voice>"
        "</speak>"
    )
    assert client._voice(ssml) == "es-ES-AlvaroNeural"
    assert "xml:lang='es-ES'" in client._locale(ssml)


def test_captions_follow_word_timings(by_lang):
    for lang in LANG_CODES:
        ov = by_lang[lang][0]
        vtt = webvtt(ov)
        assert vtt.startswith("WEBVTT") and f"Language: {lang}" in vtt
        lines = phrases(ov["script"]["words"], ov["script"]["text"])
        assert " ".join(t for _, _, t in lines) == ov["script"]["text"]
        starts = [s for s, _, _ in lines]
        assert starts == sorted(starts) and all(s < e for s, e, _ in lines)


def test_pipeline_generates_each_language_once(tmp_path):
    class Counting(FakeLLMClient):
        n = 0

        def draft(self, request):
            Counting.n += 1
            return super().draft(request)

    opts = RunOptions(seed=7, half_minutes=3.0, max_moments=1, lang="en-GB,es-ES", cache=tmp_path)
    log = run(opts, config=CrewConfig(), llm=Counting())
    assert sorted(
        oid.rsplit("-", 2)[-2] + "-" + oid.rsplit("-", 1)[-1] for oid in log.generated
    ) == [
        "en-GB",
        "es-ES",
    ]
    root = tmp_path / f"{log.match_id}-{log.digest[:8]}"
    for oid in log.generated:
        assert (root / "captions" / f"{oid}.vtt").read_text().startswith("WEBVTT")
        assert json.loads((root / "overlays" / f"{oid}.json").read_text())["gate"]["passed"]
    calls = Counting.n
    again = run(opts, config=CrewConfig(), llm=Counting())
    assert sorted(again.cached) == sorted(log.generated) and Counting.n == calls


def test_captions_handle_azure_number_and_unit_words():
    words = [
        {"text": t, "offset_ms": i * 300, "duration_ms": 250}
        for i, t in enumerate(["Una", "de", "6 opciones", "Bien"])
    ]
    lines = phrases(words, "Una de 6 opciones. ¡Bien!")
    assert [t for _, _, t in lines] == ["Una de 6 opciones.", "¡Bien!"]
