"""
Build the Data eXchange Mapper Docker image.

Usage:
    python scripts/docker_build.py
    python scripts/docker_build.py --tag dxm:dev
    python scripts/docker_build.py --kaoto-ref 2.10.0
    python scripts/docker_build.py --no-cache
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default=DEFAULT_TAG, help=f"Image tag. Default: {DEFAULT_TAG}")
    parser.add_argument("--kaoto-repo", default="https://github.com/KaotoIO/kaoto", help="Kaoto git URL")
    parser.add_argument("--kaoto-ref", default="main", help="Kaoto git ref (branch/tag/sha). Default: main")
    parser.add_argument("--no-cache", action="store_true", help="Pass --no-cache to docker build")
    parser.add_argument("--platform", default=None, help="e.g. linux/amd64 or linux/arm64")
    parser.add_argument("--engine", default=os.environ.get("DOCKER", "docker"), help="docker or podman")
    args = parser.parse_args()

    engine = shutil.which(args.engine)
    if not engine:
        print(f"ERROR: '{args.engine}' not found on PATH", file=sys.stderr)
        return 1

    cmd = [
        engine, "build",
        "-t", args.tag,
        "-f", str(REPO_ROOT / "Dockerfile"),
        "--build-arg", f"KAOTO_REPO={args.kaoto_repo}",
        "--build-arg", f"KAOTO_REF={args.kaoto_ref}",
    ]
    if args.no_cache:
        cmd.append("--no-cache")
    if args.platform:
        cmd += ["--platform", args.platform]
    cmd.append(str(REPO_ROOT))

    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
