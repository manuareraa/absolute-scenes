# Stream C → Coordinator: make `evals/` a workspace member

`evals/` now holds a package (`evals/pyproject.toml`, `chalktalk-evals`, `src/chalktalk_evals`)
and tests (`evals/tests`). The root `pyproject.toml` is coordinator-owned, so please add:

```toml
[tool.uv.workspace]
members = [..., "evals"]

[tool.uv.sources]
chalktalk-evals = { workspace = true }

[tool.pytest.ini_options]
testpaths = [..., "evals/tests"]
```
and `chalktalk-evals` to the root `dependencies`, then `uv lock`.

Until then:
- CI still exercises the harness through `crew/tests/test_offline_evals.py` (it puts
  `evals/src` on `sys.path`);
- run the eval tests with `uv run pytest evals/tests`;
- run the suite with `PYTHONPATH=evals/src uv run python -m chalktalk_evals --out report.json`.

After the change, the `sys.path` lines in `evals/tests/conftest.py` and
`crew/tests/test_offline_evals.py` can go (stream C will remove them).
