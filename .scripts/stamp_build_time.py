#!/usr/bin/env python
"""
stamp_build_time.py

Usage:
    python .scripts/stamp_build_time.py /app/build_info.json

Behavior:
- Loads the given JSON.
- Sets/updates "build_time" to current UTC ISO8601 (Z).
- Does NOT touch any other keys (including "git_sha" or "_git_sha").
- Writes the file back prettified.
"""
import sys, json
from pathlib import Path
from datetime import datetime, timezone

def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "build_info.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    # ISO8601 UTC
    data["build_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Stamped build_time in {path}")

if __name__ == "__main__":
    main()
