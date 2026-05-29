"""
Run the Data eXchange Mapper Docker container.

Usage:
    python scripts/docker_run.py
    python scripts/docker_run.py --port 8080
    python scripts/docker_run.py --detach
    python scripts/docker_run.py --workspace ./workspace
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TAG = os.environ.get("DXM_IMAGE", "data-exchange-mapper:latest")
DEFAULT_NAME = "dxm"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default=DEFAULT_TAG, help=f"Image tag. Default: {DEFAULT_TAG}")
    parser.add_argument("--port", type=int, default=5000, help="Host port. Default: 5000")
    parser.add_argument("--name", default=DEFAULT_NAME, help=f"Container name. Default: {DEFAULT_NAME}")
    parser.add_argument("--detach", "-d", action="store_true", help="Run detached")
    parser.add_argument("--workspace", default=None,
                        help="Mount this host directory at /app/workspace (sandboxed file API).")
    parser.add_argument("--engine", default=os.environ.get("DOCKER", "docker"), help="docker or podman")
    parser.add_argument("--rm", dest="autoremove", action="store_true", default=True,
                        help="(default) auto-remove container on exit")
    parser.add_argument("--no-rm", dest="autoremove", action="store_false",
                        help="Do not auto-remove the container on exit")
    args = parser.parse_args()

    engine = shutil.which(args.engine)
    if not engine:
        print(f"ERROR: '{args.engine}' not found on PATH", file=sys.stderr)
        return 1

    cmd = [engine, "run", "--name", args.name, "-p", f"{args.port}:5000"]
    if args.autoremove:
        cmd.append("--rm")
    if args.detach:
        cmd.append("-d")
    else:
        cmd.append("-it")

    if args.workspace:
        host = Path(args.workspace).resolve()
        host.mkdir(parents=True, exist_ok=True)
        cmd += ["-v", f"{host}:/app/workspace"]

    cmd.append(args.tag)

    print("$ " + " ".join(cmd), flush=True)
    if not args.detach:
        print(f"\nOpen http://localhost:{args.port}/  (Ctrl+C to stop)\n", flush=True)
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
