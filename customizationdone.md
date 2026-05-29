# Customizations Done

This document tracks the customizations layered on top of upstream
[KaotoIO/kaoto](https://github.com/KaotoIO/kaoto) to produce the
**Data eXchange Mapper** experience.

> **Important:** these patches live inside `.kaoto-src/`, which is
> gitignored. They are **not** preserved across
> `python scripts/setup_kaoto.py --clean` (full re-clone). See
> [Persisting the customizations](#persisting-the-customizations)
> below for options.

> **Update:** Option A below has been **implemented**. The diff is
> committed at [`scripts/kaoto.patch`](scripts/kaoto.patch) and is
> reapplied automatically by both `scripts/setup_kaoto.py` and the
> `Dockerfile`. So a fresh `--clean` re-clone (or a `docker build`)
> rebrands Kaoto end-to-end without manual editing.

## How the Kaoto DataMapper gets into the running app

```
GitHub: KaotoIO/kaoto  ──git clone──►  .kaoto-src/  (gitignored, ~2 GB)
                                              │
                                              │  corepack yarn install
                                              │  corepack yarn workspace @kaoto/kaoto build
                                              ▼
                                       .kaoto-src/packages/ui/dist/   (built static SPA, ~6 MB)
                                              │
                                              │  FRONTEND_DIST=...
                                              ▼
                                          Flask app.py
                                              │
                                              │  GET /  → serves dist/index.html
                                              │  GET /assets/* → serves bundled JS/CSS
                                              ▼
                                            Browser
```

## What's in this repo (small — your code)

| File / dir                  | Purpose                                                                 |
| --------------------------- | ----------------------------------------------------------------------- |
| `app.py`                    | Flask server that serves the built Kaoto bundle as static files         |
| `scripts/setup_kaoto.py`    | Clones Kaoto + runs yarn build with our build-time flags                |
| `scripts/run_app.py`        | Launches Flask with `FRONTEND_DIST` pointed at the built `dist/`        |
| `scripts/setup-kaoto.ps1`   | Legacy PowerShell equivalent of `setup_kaoto.py`                        |
| `sample/`                   | Demo JSON Schema + XSD                                                  |
| `requirements.txt`          | Just Flask                                                              |
| `docs/screenshots/`         | README images                                                           |
| `customizationdone.md`      | This document                                                           |

## What's NOT in this repo (pulled fresh on each setup)

| Path                                  | Where it comes from                                           | Why it's gitignored                                  |
| ------------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------- |
| `.kaoto-src/`                         | `git clone https://github.com/KaotoIO/kaoto`                  | ~2 GB; upstream-maintained; would dwarf the repo     |
| `.kaoto-src/packages/ui/dist/`        | `corepack yarn build`                                         | Build artifact — re-generated from source            |
| `.venv/`                              | `python -m venv`                                              | User-specific                                        |

## Build-time configuration

Two Vite env vars baked into the bundle by `setup_kaoto.py`:

| Env var                            | Effect                                                                                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `VITE_ENABLE_DATAMAPPER_DEBUGGER`  | Replaces the "DataMapper cannot be configured in browser" placeholder at `#/datamapper` with the real standalone DataMapper page. |
| `VITE_DATAMAPPER_ONLY`             | Hides the left navigation + makes the DataMapper the index route, so the app is DataMapper-only.        |

## The six patches we apply to Kaoto

These files in the upstream clone are modified by hand and **revert on
a clean re-clone**:

| #  | File                                                                                  | Change                                                                                   |
| -- | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| 1  | `src/router.tsx`                                                                       | Read `VITE_DATAMAPPER_ONLY`; when set, index route renders the DataMapper debugger page. |
| 2  | `src/layout/Shell.tsx`                                                                 | In DataMapper-only mode, omit the `sidebar` prop on `<Page>` so the left nav disappears. |
| 3  | `src/layout/TopBar.tsx`                                                                | Accept `hideNavToggle`; replace the Kaoto logo image with the text **"Data eXchange Mapper"**. |
| 4  | `src/components/DataMapper/debug/MainMenuToolbarItem.tsx`                              | Dropdown label changed from "DataMapper Debugger" to **"DataMapper - UI"**.              |
| 5  | `src/components/DataMapper/debug/ToggleDebugToolbarItem.tsx`                           | Bug icon swapped for **`CogIcon`** (gear); aria-label / tooltip changed to **"Actions"**. |
| 6  | `index.html`                                                                           | Browser tab title changed from "Kaoto" to **"Data eXchange Mapper"**.                    |

## Persisting the customizations

Currently the patches live only inside the gitignored `.kaoto-src/`.
After `python scripts/setup_kaoto.py --clean`, they disappear. Two
clean ways to make them reproducible:

### Option A — Patch file (recommended)

1. After patching the files in `.kaoto-src/`, run:
   ```bash
   cd .kaoto-src
   git diff > ../scripts/kaoto.patch
   ```
2. Commit `scripts/kaoto.patch` to this repo.
3. Update `scripts/setup_kaoto.py` to run, just before
   `yarn install`:
   ```python
   run(["git", "apply", "../scripts/kaoto.patch"], cwd=kaoto_src)
   ```
4. On every fresh `setup_kaoto.py` run, the patches reapply.

Pros: tiny diff committed; easy to review; works against any Kaoto
upstream ref provided the surrounding code hasn't drifted.

Cons: when upstream changes around the patched lines, the patch may
fail to apply; you'll need to refresh it.

### Option B — Fork Kaoto

1. Fork `KaotoIO/kaoto` on GitHub.
2. Commit the 6 changes to your fork on a `data-exchange-mapper`
   branch.
3. Run:
   ```bash
   python scripts/setup_kaoto.py --repo https://github.com/<you>/kaoto --ref data-exchange-mapper
   ```

Pros: changes are first-class git commits; can be rebased against
upstream.

Cons: maintaining a fork is more work; need to keep
`--repo` / `--ref` pinned in docs.

## Current state

- Upstream Kaoto: `main` branch (configurable via `--ref` /
  `--kaoto-ref`).
- Patches: captured in [`scripts/kaoto.patch`](scripts/kaoto.patch)
  (~7 KB, 6 files) and applied automatically by:
  - `scripts/setup_kaoto.py` (after clone, before `yarn install`)
  - `Dockerfile` stage 1 (after `git clone`, before `yarn install`)
- `setup_kaoto.py` is idempotent: if `index.html` already shows
  "Data eXchange Mapper", the patch step is skipped.
- A fresh `--clean` rebuild or a `docker build --no-cache` reproduces
  the branded UI from scratch.

## Docker workflow

The repo ships a multi-stage `Dockerfile`:

1. **Stage `kaoto-builder`** — `node:20-bookworm-slim`. Clones Kaoto
   at `KAOTO_REF` (build-arg, default `main`), copies in
   `scripts/kaoto.patch`, runs `git apply`, then
   `corepack yarn install` + `corepack yarn workspace @kaoto/kaoto build`
   with the two `VITE_*` env vars set.
2. **Stage `runtime`** — `python:3.12-slim-bookworm`. Installs Flask
   + gunicorn, copies `app.py`, `sample/`, and the built SPA from
   stage 1. Runs as non-root user `app` and serves via gunicorn on
   port 5000.

Helpers:

- `python3 scripts/docker_build.py` — wraps `docker build`. Forwards
  `--kaoto-ref`, `--tag`, `--no-cache`, `--platform`, `--engine`.
- `python3 scripts/docker_run.py` — wraps `docker run`. Supports
  `--port`, `--detach`, `--workspace` (host mount → `/app/workspace`),
  and `--engine docker|podman`.
