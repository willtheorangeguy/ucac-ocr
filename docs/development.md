# Development

## Local environment

Use Python 3.14 and follow the source [installation](./installation.md). Install the complete pinned [requirements.lock](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/requirements.lock) into a virtual environment. The repository has no package build metadata or separate development dependency group; the lock includes pytest and pytest-asyncio.

Run the web app and worker separately from the checkout, using one shared development `DATA_DIR`. Keep development data separate from operator data. The [architecture guide](./architecture.md) maps modules and durable storage boundaries.

## Checks for a change

```sh
python -m pytest -q
python -m pip check
node --check app/static/app.js
```

Node is optional for the JavaScript syntax check, not an application runtime dependency. There are no configured formatter, linter, or static type-check commands in this checkout. Browser validation requires extra tooling; see [testing](./testing.md). Do not present saved historical reports as a fresh run.

Tests use a temporary data directory and a mock local Ollama HTTP server. The autouse fixture selects the historical strict profile; tests for fast counts explicitly select current rough settings. Some additional validation paths require operator-supplied workbook/photo fixtures and can skip when unavailable. Review skip reasons before claiming full coverage.

## Working on durable behavior

Keep database transactions outside long HTTP/model requests. Preserve raw evidence and reviewed cells when changing reconciliation. Treat blank, zero, missing observations, failed reads, and conflicts as separate states. Test source version races and revision changes when editing preprocessing/export behavior. New settings belong in `app/config.py`, `.env.example` where useful, and [configuration](./configuration.md).

When changing workbook output, preserve unrelated OOXML parts and verify calendar/time anchors, continuation, and monthly column mapping. The bundled monthly template's provenance is documented in [app/assets/README.md](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/app/assets/README.md).

## Documentation preview

Create a separate virtual environment for documentation dependencies. From the checkout, clone the shared repository and run its preview helper:

```bash
git clone --depth 1 https://github.com/willtheorangeguy/mkdocs .mkdocs-shared
python3 -m venv /tmp/ucac-docs-venv
. /tmp/ucac-docs-venv/bin/activate
pip install -r .mkdocs-shared/shared/requirements-docs.txt
bash .mkdocs-shared/scripts/docs-serve.sh --build
```

The helper creates `.mkdocs-shared`, stages ignored design assets, and runs `mkdocs build --strict`. Without `--build`, it serves a local preview. Set `PORT=8001` if the application already uses 8000. On Windows use `.mkdocs-shared/scripts/docs-serve.ps1 -Build` in the documentation environment.

The [CI/CD guide](ci-cd.md) covers documentation deployment and release containers.

## Contributing

Use the org-wide [Contributing Guide](https://github.com/willtheorangeguy/.github/blob/main/CONTRIBUTING.md) and [Code of Conduct](https://github.com/willtheorangeguy/.github/blob/main/CODE_OF_CONDUCT.md). Include the user-visible behavior, relevant checks and skip reasons, and any data migration/recovery implications. Record discovered defects in [internal/known-issues.md](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/docs/internal/known-issues.md); do not silently resolve code issues in a documentation change.
