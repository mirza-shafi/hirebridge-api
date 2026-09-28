"""Write the OpenAPI schema to a file.

The committed `openapi.json` is the contract the web client generates from. CI regenerates
and diffs it, so a route change that is not reflected in the schema fails the build rather
than silently breaking the frontend's types.

    uv run python scripts/export_openapi.py openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    schema = app.openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    paths = len(schema.get("paths", {}))
    print(f"wrote {target} ({paths} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
