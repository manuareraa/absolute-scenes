"""Canonical JSON and output hashes for claim provenance.

A claim's ``tool_call.output_hash`` is ``"sha256:" + hex`` over the canonical JSON of the
tool output. The Verifier re-runs the tool and compares hashes (exact) or values (within
the claim's tolerance). Floats are rounded before hashing so that the hash does not depend
on the last bits of floating-point arithmetic.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

FLOAT_DIGITS = 4


def normalise(obj: Any, digits: int = FLOAT_DIGITS) -> Any:
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError("non-finite float in tool output")
        value = round(obj, digits)
        return 0.0 if value == 0 else value
    if isinstance(obj, dict):
        return {str(k): normalise(v, digits) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [normalise(v, digits) for v in obj]
    if getattr(obj, "ndim", 0) > 0:  # numpy array
        return normalise(obj.tolist(), digits)
    if hasattr(obj, "item"):  # numpy scalar
        return normalise(obj.item(), digits)
    raise TypeError(f"cannot hash {type(obj).__name__}")


def canonical_json(obj: Any) -> str:
    return json.dumps(normalise(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def output_hash(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(obj).encode()).hexdigest()
