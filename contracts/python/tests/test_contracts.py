import json
from pathlib import Path

import pytest
from chalktalk_contracts import SCHEMA_NAMES, is_valid, validate
from chalktalk_contracts.models import (
    ask_event_schema,
    claim_schema,
    event_schema,
    frame_schema,
    overlay_schema,
    show_schema,
)
from jsonschema import ValidationError

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
MODELS = {
    "frame": frame_schema.Frame,
    "event": event_schema.Event,
    "claim": claim_schema.Claim,
    "overlay": overlay_schema.Overlay,
    "show": show_schema.Show,
    "ask-event": ask_event_schema.AskEvent,
}


def load(path: Path):
    return json.loads(path.read_text())


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_valid_example_passes_schema(name):
    validate(name, load(EXAMPLES / "valid" / f"{name}.json"))


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_valid_example_round_trips_through_pydantic(name):
    data = load(EXAMPLES / "valid" / f"{name}.json")
    model = MODELS[name].model_validate(data)
    dumped = json.loads(model.model_dump_json(exclude_unset=True))
    validate(name, dumped)


@pytest.mark.parametrize(
    "path", sorted((EXAMPLES / "invalid").glob("*.json")), ids=lambda p: p.stem
)
def test_invalid_example_is_rejected(path):
    name = path.name.split(".", 1)[0]
    assert not is_valid(name, load(path))
    with pytest.raises(ValidationError):
        validate(name, load(path))


def test_every_contract_has_an_invalid_example():
    covered = {p.name.split(".", 1)[0] for p in (EXAMPLES / "invalid").glob("*.json")}
    assert covered == set(SCHEMA_NAMES)


def test_unknown_contract_name():
    with pytest.raises(KeyError):
        validate("nope", {})
