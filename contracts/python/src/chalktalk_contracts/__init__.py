"""ChalkTalk shared contracts.

The JSON Schemas in ``contracts/schemas`` are the source of truth. Pydantic models in
``chalktalk_contracts.models`` are generated from them by ``scripts/gen_contracts.sh``;
never edit the generated files by hand.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

__version__ = "0.0.0"

SCHEMA_NAMES = ("frame", "event", "claim", "overlay", "show", "ask-event")

# Editable installs see the repo copy; built wheels carry a packaged copy.
_CANDIDATES = (
    Path(__file__).resolve().parents[3] / "schemas",
    Path(__file__).resolve().parent / "schemas",
)


def schema_dir() -> Path:
    for path in _CANDIDATES:
        if (path / "frame.schema.json").exists():
            return path
    raise FileNotFoundError("contracts/schemas not found")


@cache
def _registry() -> Registry:
    resources = []
    for name in SCHEMA_NAMES:
        doc = json.loads((schema_dir() / f"{name}.schema.json").read_text())
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


@cache
def validator(name: str) -> Draft202012Validator:
    if name not in SCHEMA_NAMES:
        raise KeyError(f"unknown contract {name!r}; expected one of {SCHEMA_NAMES}")
    schema = _registry().contents(f"{name}.schema.json")
    return Draft202012Validator(schema, registry=_registry())


def validate(name: str, instance: Any) -> None:
    """Raise ``jsonschema.ValidationError`` if ``instance`` breaks contract ``name``."""
    validator(name).validate(instance)


def is_valid(name: str, instance: Any) -> bool:
    return validator(name).is_valid(instance)
