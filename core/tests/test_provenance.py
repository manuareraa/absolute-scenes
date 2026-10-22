import numpy as np
import pytest
from chalktalk_core.provenance import canonical_json, normalise, output_hash


def test_hash_ignores_key_order_and_float_noise():
    a = {"b": 1.000001, "a": [np.float32(0.5), np.int64(2)]}
    b = {"a": [0.5, 2], "b": 1.0}
    assert output_hash(a) == output_hash(b)
    assert output_hash(a).startswith("sha256:") and len(output_hash(a)) == 71
    assert canonical_json(b) == '{"a":[0.5,2],"b":1.0}'


def test_normalise_rejects_bad_values():
    assert normalise(-0.00001) == 0.0
    assert normalise(np.arange(3)) == [0, 1, 2]
    with pytest.raises(ValueError):
        normalise(float("nan"))
    with pytest.raises(TypeError):
        normalise(object())
