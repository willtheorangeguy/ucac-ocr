# Pool Headcount — Development

## Local environment

Use Python 3.14 and follow the source [installation](./installation.md). Install the complete pinned [requirements.lock](../requirements.lock) into a virtual environment. The repository has no package build metadata or separate development dependency group; the lock includes pytest and pytest-asyncio.

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

When changing workbook output, preserve unrelated OOXML parts and verify calendar/time anchors, continuation, and monthly column mapping. The bundled monthly template's provenance is documented in [app/assets/README.md](../app/assets/README.md).

## Release pipeline

[Publish release container](../.github/workflows/publish-container.yml) runs when a GitHub release is published, rather than on every push or pull request. It:

1. Checks out the release tag and generates version-pinned deployment files.
2. Builds a Linux AMD64 test image and runs pytest with the checkout mounted read-only.
3. Publishes Linux AMD64/ARM64 images to `ghcr.io/willtheorangeguy/ucac-ocr` using the repository `GITHUB_TOKEN` with package-write permission.
4. Starts the published image with standalone Compose and waits for service health.
5. Attaches `compose.yaml`, `default.env`, and the ZIP preserving `.env` to the release, then cleans up its temporary smoke-test volume.

The release generator accepts `vMAJOR.MINOR.PATCH` with an optional prerelease suffix. Stable `v0.1.0` publishes `0.1.0`, `v0.1.0`, `0.1`, and `latest`; prereleases do not update minor/latest tags. Attachments are generated from `.env.example`, never an operator's `.env`.

Generate assets locally without publishing:

```sh
python scripts/prepare_release.py v0.1.0 ghcr.io/willtheorangeguy/ucac-ocr /tmp/ucac-release-files
```

Keep generated output outside the source tree; release publishing is a separate maintainer action. The workflow's standalone health check does not establish live OCR accuracy or GPU performance.

## Contributing

Use the org-wide [Contributing Guide](https://github.com/willtheorangeguy/.github/blob/main/CONTRIBUTING.md) and [Code of Conduct](https://github.com/willtheorangeguy/.github/blob/main/CODE_OF_CONDUCT.md). Include the user-visible behavior, relevant checks and skip reasons, and any data migration/recovery implications. Record discovered defects in [internal/known-issues.md](./internal/known-issues.md); do not silently resolve code issues in a documentation change.
