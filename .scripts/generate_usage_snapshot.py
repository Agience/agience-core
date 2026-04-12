from __future__ import annotations

import runpy
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    backend_script = _repo_root() / "backend" / "scripts" / "generate_usage_snapshot.py"
    runpy.run_path(str(backend_script), run_name="__main__")