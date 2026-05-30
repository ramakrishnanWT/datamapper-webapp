# Current plan

Goal: package a reproducible Data eXchange Mapper web app by serving a
patched Kaoto DataMapper build from Flask.

## Current status

| Area | State |
| --- | --- |
| Flask static host and health endpoint | Done |
| Sandboxed `/api/files/*` workspace API | Done |
| Sample listing and copy endpoints | Done |
| Kaoto clone, patch, and build script | Done |
| Docker multi-stage build and run helpers | Done |
| Fast backend tests and CI workflow | Done |
| Kaoto version pinning | Planned |
| Patch drift check against the selected Kaoto ref | Planned |
| File API auth and upload limits for shared deployments | Planned |

## Architecture

The repository does not maintain a separate React frontend scaffold. The
frontend is the upstream Kaoto UI, cloned into `.kaoto-src/`, patched by
`scripts/kaoto.patch`, and built into `.kaoto-src/packages/ui/dist/`.
Flask serves that built directory through `FRONTEND_DIST`.

```text
KaotoIO/kaoto
  -> scripts/setup_kaoto.py clones and applies scripts/kaoto.patch
  -> corepack yarn workspace @kaoto/kaoto build
  -> .kaoto-src/packages/ui/dist
  -> Flask app.py serves the static SPA and backend file API
```

## Near-term improvements

1. Pin the default Kaoto ref in `scripts/setup_kaoto.py` and `Dockerfile`
   to a known-good tag or commit SHA instead of tracking upstream `main`.
2. Teach `scripts/setup_kaoto.py` to detect when an existing `.kaoto-src`
   checkout does not match the requested `--repo` or `--ref`, then either
   check out the requested ref or ask for `--clean`.
3. Add a lightweight CI job that verifies `scripts/kaoto.patch` still
   applies to the pinned Kaoto ref.
4. Add token-based protection and request size limits before exposing the
   file API beyond local development.
