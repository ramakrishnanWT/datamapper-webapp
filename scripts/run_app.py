"""
Launches the Flask app with FRONTEND_DIST pointing at the built Kaoto UI.

Usage:
    python scripts/run_app.py
    python scripts/run_app.py --port 8000
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default=os.environ.get("FLASK_PORT", "5000"))
    parser.add_argument(
        "--frontend-dist",
        default=os.environ.get("FRONTEND_DIST") or str(REPO_ROOT / ".kaoto-src" / "packages" / "ui" / "dist"),
    )
    args = parser.parse_args()

    dist = Path(args.frontend_dist).resolve()
    if not dist.exists():
        print(f"ERROR: FRONTEND_DIST does not exist: {dist}", file=sys.stderr)
        print("Run: python scripts/setup_kaoto.py", file=sys.stderr)
        return 1

    os.environ["FRONTEND_DIST"] = str(dist)
    os.environ["FLASK_PORT"] = str(args.port)

    # Run app.py as __main__ so its `if __name__ == "__main__": app.run(...)` fires.
    import runpy
    sys.path.insert(0, str(REPO_ROOT))
    runpy.run_path(str(REPO_ROOT / "app.py"), run_name="__main__")

    return 0


if __name__ == "__main__":
    sys.exit(main())
