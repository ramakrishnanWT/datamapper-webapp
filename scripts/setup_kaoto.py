"""
Cross-platform Python equivalent of scripts/setup-kaoto.ps1.

Clones the Kaoto repository and builds the Kaoto Online UI so that Flask
can serve it as static assets. After this finishes, run app.py with
FRONTEND_DIST pointing at the built dist/ folder.

Usage:
    python scripts/setup_kaoto.py                  # default: main branch
    python scripts/setup_kaoto.py --ref 2.10.0     # any branch / tag / sha
    python scripts/setup_kaoto.py --skip-install   # rebuild only
    python scripts/setup_kaoto.py --clean          # delete .kaoto-src first

Prereqs (PATH):
    git, node (>=20), corepack
Optional env overrides:
    KAOTO_REPO   default https://github.com/KaotoIO/kaoto
    KAOTO_SRC    default <repo>/.kaoto-src
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KAOTO_REPO = os.environ.get("KAOTO_REPO", "https://github.com/KaotoIO/kaoto")
DEFAULT_KAOTO_SRC = Path(os.environ.get("KAOTO_SRC", REPO_ROOT / ".kaoto-src"))
KAOTO_PATCH = Path(__file__).resolve().parent / "kaoto.patch"

# Build-time Vite flags baked into the Kaoto bundle.
BUILD_ENV = {
    # Replace the "DataMapper cannot be configured in browser" placeholder
    # with the real standalone DataMapperDebugger page at #/datamapper.
    "VITE_ENABLE_DATAMAPPER_DEBUGGER": "true",
    # Hide the left nav + other Kaoto pages; index route renders the
    # DataMapper directly.
    "VITE_DATAMAPPER_ONLY": "true",
}


def banner(msg: str) -> None:
    print(f"\n=== {msg} ===", flush=True)


def run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    """Run a subprocess, streaming output. Raise on non-zero exit."""
    print(f"$ {' '.join(cmd)}" + (f"   (cwd={cwd})" if cwd else ""), flush=True)
    # On Windows, `corepack` / `git` resolve as .cmd shims -> need shell=True
    # only when invoking by bare name; using shutil.which avoids that.
    resolved = shutil.which(cmd[0])
    if resolved is None:
        raise SystemExit(f"ERROR: '{cmd[0]}' not found on PATH")
    full_cmd = [resolved, *cmd[1:]]
    completed = subprocess.run(full_cmd, cwd=cwd, env=env)
    if completed.returncode != 0:
        raise SystemExit(f"ERROR: command failed with exit code {completed.returncode}")


def ensure_yarn() -> None:
    banner("Verifying corepack (yarn)")
    run(["corepack", "yarn", "--version"])


def clone_or_update(kaoto_src: Path, ref: str, repo_url: str) -> None:
    if kaoto_src.exists():
        banner(f"Kaoto checkout already present at {kaoto_src}")
        return
    banner(f"Cloning Kaoto ({ref}) into {kaoto_src}")
    run(
        [
            "git", "clone",
            "--depth", "1",
            "--branch", ref,
            repo_url,
            str(kaoto_src),
        ]
    )


def apply_patch(kaoto_src: Path, patch: Path) -> None:
    if not patch.exists():
        print(f"  (no patch file at {patch}; skipping)")
        return
    # Detect already-applied patch by checking the title-string we change.
    index_html = kaoto_src / "packages" / "ui" / "index.html"
    if index_html.exists() and "Data eXchange Mapper" in index_html.read_text(encoding="utf-8"):
        banner("Kaoto patch already applied; skipping")
        return
    banner(f"Applying {patch.name}")
    run(["git", "apply", "--whitespace=nowarn", str(patch)], cwd=kaoto_src)


def yarn_install(kaoto_src: Path) -> None:
    banner("yarn install (this takes a while — 1800+ packages)")
    run(["corepack", "yarn", "install"], cwd=kaoto_src)


def yarn_build(kaoto_src: Path) -> None:
    banner("yarn workspace @kaoto/kaoto build (full Kaoto Online app)")
    env = os.environ.copy()
    env.update(BUILD_ENV)
    run(
        ["corepack", "yarn", "workspace", "@kaoto/kaoto", "build"],
        cwd=kaoto_src,
        env=env,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default="main", help="Git ref (branch/tag/sha) of Kaoto to check out. Default: main")
    parser.add_argument("--repo", default=DEFAULT_KAOTO_REPO, help="Git URL of Kaoto repo")
    parser.add_argument("--kaoto-src", default=str(DEFAULT_KAOTO_SRC), help="Where to clone Kaoto")
    parser.add_argument("--skip-install", action="store_true", help="Skip yarn install (just rebuild)")
    parser.add_argument("--skip-build", action="store_true", help="Skip yarn build")
    parser.add_argument("--skip-patch", action="store_true", help="Skip applying scripts/kaoto.patch")
    parser.add_argument("--clean", action="store_true", help="Delete .kaoto-src before cloning")
    args = parser.parse_args()

    kaoto_src = Path(args.kaoto_src).resolve()

    if args.clean and kaoto_src.exists():
        banner(f"Removing {kaoto_src}")
        shutil.rmtree(kaoto_src, ignore_errors=False)

    ensure_yarn()
    clone_or_update(kaoto_src, args.ref, args.repo)

    if not args.skip_patch:
        apply_patch(kaoto_src, KAOTO_PATCH)

    if not args.skip_install:
        yarn_install(kaoto_src)
    if not args.skip_build:
        yarn_build(kaoto_src)

    dist = kaoto_src / "packages" / "ui" / "dist"
    print()
    print(f"Done. Built Kaoto Online at:\n  {dist}")
    print()
    print("Start the Flask server with:")
    if os.name == "nt":
        print(f'  $env:FRONTEND_DIST = "{dist}"')
        print("  python app.py")
    else:
        print(f"  export FRONTEND_DIST='{dist}'")
        print("  python app.py")
    print()
    print("Then open http://127.0.0.1:5000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
