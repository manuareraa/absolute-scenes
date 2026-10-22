import sys
from pathlib import Path

# evals/ is not a uv workspace member yet (see docs/notes/c-evals-workspace.md).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
