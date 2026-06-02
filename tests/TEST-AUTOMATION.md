# Test Automation — Data eXchange Mapper (DXM)

> Covers the test strategy, tooling, test inventory, and CI integration for the `datamapper-webapp` project.

---

## 1. Test Strategy

| Layer | Tooling | Scope |
|---|---|---|
| Unit / integration (backend) | `pytest` | Flask routes, sandboxing, file API, sample API |
| Contract (API) | `pytest` + Flask test client | All REST endpoints, error responses |
| End-to-end (UI) | Playwright (planned) | Browser smoke test: load UI, attach schema, draw mapping, export XSLT |
| Static analysis | `ruff` / `mypy` | Code quality, type safety |
| Container smoke test | `docker run` + `curl` | Image boots, `/api/health` returns 200 |

---

## 2. Project Layout

```text
datamapper-webapp/
├── tests/
│   ├── test_app.py          # backend unit & integration tests (pytest)
│   └── e2e/                 # (planned) Playwright end-to-end tests
│       ├── conftest.py
│       └── test_ui_smoke.py
├── requirements.txt          # runtime deps
└── requirements-dev.txt      # pytest, playwright, ruff, mypy, etc.
```

---

## 3. Running the Tests

### 3.1 Backend tests (fast, no browser)

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all backend tests
pytest tests/test_app.py -v

# Run with coverage
pytest tests/test_app.py --cov=app --cov-report=term-missing
```

### 3.2 End-to-end tests (browser, requires running app)

```bash
# Install Playwright browsers (one-time)
playwright install chromium

# Start the app in one terminal
python scripts/run_app.py

# Run E2E tests in another terminal
pytest tests/e2e/ -v --base-url http://localhost:5000
```

### 3.3 Container smoke test

```bash
# Build the image
python scripts/docker_build.py

# Run and probe the health endpoint
python scripts/docker_run.py &
sleep 5
curl -sf http://localhost:5000/api/health | python -m json.tool
```

---

## 4. Test Inventory

### 4.1 Backend — `tests/test_app.py`

| Test | What it covers | Spec ref |
|---|---|---|
| `test_default_frontend_dist_points_to_kaoto_build` | `FRONTEND_DIST` resolves to `.kaoto-src/packages/ui/dist` when env var is absent | S-01 |
| `test_missing_frontend_page_shows_current_setup_commands` | Setup instructions shown when dist is missing | S-01 |
| `test_file_api_crud_and_traversal_rejection` | PUT / GET / list / path-traversal 400 | B-02, B-03, B-01, B-06 |
| `test_sample_copy_uses_sandbox_workspace` | Sample listing and copy into workspace | B-07, B-08 |

### 4.2 Planned — API contract

| Test (planned) | Spec ref |
|---|---|
| `test_health_returns_ok` | B-09 |
| `test_put_creates_nested_dirs` | B-03 |
| `test_delete_file` | B-04 |
| `test_head_exists_and_missing` | B-05 |
| `test_path_traversal_variants` (multiple payloads) | B-06, NF-01 |
| `test_list_returns_sorted_paths` | B-01 |

### 4.3 Planned — End-to-end (Playwright)

| Test (planned) | What it covers |
|---|---|
| `test_ui_loads` | `/` returns 200, Kaoto canvas visible |
| `test_attach_json_schema` | Upload `.schema.json`, field tree appears |
| `test_attach_xsd` | Upload `.xsd`, output field tree appears |
| `test_draw_mapping_and_export_xslt` | Connect fields, download `.xsl`, validate it is non-empty XML |
| `test_workspace_persists_after_reload` | Reload page, mapping state restored |

---

## 5. Test Data

| File | Used by |
|---|---|
| `sample/order-input.schema.json` | Schema attachment tests |
| `sample/order-output.xsd` | XSD attachment tests |
| `sample/order.json` | Sample copy tests |
| `workspace/order.json` | Baseline workspace state |

---

## 6. CI Integration

The following GitHub Actions workflow runs on every push and pull request:

```yaml
# .github/workflows/ci.yml (example)
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements-dev.txt
      - run: pytest tests/test_app.py -v --cov=app --cov-report=xml
      - uses: codecov/codecov-action@v4   # optional

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff mypy
      - run: ruff check .
      - run: mypy app.py
```

---

## 7. Coverage Targets

| Layer | Current | Target |
|---|---|---|
| Backend (lines) | ~80 % | 90 % |
| API contract (endpoints) | 4 / 9 | 9 / 9 |
| End-to-end (critical paths) | 0 / 5 | 5 / 5 |

---

## 8. Adding a New Test

1. Identify the spec requirement ID from [SPEC.md](../docs/SPEC.md).
2. Add the test to `tests/test_app.py` (backend) or `tests/e2e/` (browser).
3. Reference the spec ID in the test's docstring.
4. Update the **Test Inventory** table in this document.
5. Run `pytest` locally to confirm green before opening a PR.
