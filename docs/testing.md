# Pool Headcount — Testing and Calibration

## Automated regression suite

From an installed source checkout:

```sh
python -m pytest -q
```

The suite covers workbook fidelity and cell anchors, monthly layout, continuation, date/row schemas, numeric normalization, blank/zero/copy-down behavior, ZIP/image ingestion, geometry/corner races, review protection, streaming failures/timeouts, worker ownership/restart, export recovery, backups, web routes, and release deployment assets. Tests normally use temporary storage and mock Ollama responses rather than the real model.

The checked-in legacy workbook and October 9 photo live in [tests/fixtures](../tests/fixtures). Extra operator workbook validation can be skipped when the fixture is absent. The [conftest](../tests/conftest.py) autouse profile is strict, so the suite is not a blanket measurement of the default single-pass profile's OCR accuracy.

[VALIDATION.md](../VALIDATION.md) is a chronological historical record. Saved XML/JSON artifacts in [validation](../validation) include failed runs as well as corrected runs. Their dates, environments, and scopes matter: do not add their test counts together or treat them as current CI results.

## Browser and geometry checks

The standalone browser script uses mocked status/write APIs and does not perform live OCR:

```powershell
.\.venv\Scripts\python.exe validation/corner_browser_check.py C:\path\to\chrome.exe
```

It requires Chromium and `websocket-client`, which is additional to `requirements.lock`. Checks include four-click saving, scaled coordinates, partial-selection retention through polling, photo switching, and desktop/mobile views. The scripts and historical screenshots are in `validation/`.

`validation/fuzzy_rows_check.py` reproduces geometry checks from externally downloaded source PNGs and API metadata; inspect its path expectations before running. Those results establish grid/crop success on the supplied photos, not count accuracy. `validation/docker_smoke_check.py` is a live deployment helper with environment-specific workbook/browser paths, not part of ordinary isolated pytest.

## Live calibration

The built-in benchmark sends crops to the configured Ollama server and creates durable records. Use a separate data directory with no running worker. It checks a date and the manually checked first row of one consented photo, not a whole sheet or month.

The command assumes B-pass tasks exist, but the default profile disables them. For this benchmark, explicitly enable verification and detailed readings before running. In a POSIX shell:

```sh
DATA_DIR=/tmp/ucac-calibration-data ROUGH_COUNTS=false VERIFICATION=always \
  python -m app.calibration --output /tmp/ucac-calibration-output
```

Choose fresh directories. In PowerShell, set the corresponding `$env:DATA_DIR`, `$env:ROUGH_COUNTS`, and `$env:VERIFICATION` variables in the calibration terminal. `THINK=true` is optional and requires a thinking-capable model. The compatibility defect is recorded in [known issues](./internal/known-issues.md).

The benchmark calls preflight, imports the legacy fixture/photo, applies the known corners, creates A/B crops, and uses the worker's lock/owner mechanism for inference. Reports contain model metadata, request options, validated results/errors, and date/first-row comparisons. It uses no cloud service, but crops do leave the application host for the configured Ollama endpoint.

## Validation still needed

The historical live check verified the legacy reference photo's first row (Public 0, External blank, Internal 32, Dry 2). It does not establish accuracy for new-format handwritten forms or a representative month.

Collect 10–20 diverse manually checked sheets and compare profiles at 8K/16K/32K context with thinking on/off. Measure exact numeric and blank/zero accuracy, date/time placement errors, review workload, and missed automatically accepted errors. Record model residency and timing/token metrics. Native Excel/LibreOffice print rendering and successful optional recalculation need independent validation. See [roadmap](./roadmap.md).
