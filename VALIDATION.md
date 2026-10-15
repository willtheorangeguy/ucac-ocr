# Validation — October 14, 2026

> Historical validation record, retained with its original results and limitations. Current test procedures and calibration prerequisites are in [docs/testing.md](docs/testing.md); these saved results do not represent a new run.

## Fuzzy row geometry — October 15, 2026

The grid-6 matcher combines evidence from five strips across each table, corrects
residual row slant, merges duplicate separators, and interpolates small internal
gaps from neighboring row spacing. It tolerates approximate corner padding and
uneven rows, while requiring the supported morning/afternoon/full-day schedule.
Large missing regions and blank pages remain rejected. Slanted column fallback
requires continuous line support so printed time digits do not become borders.
Saved page geometry records the fitted row boundaries and detector version.

All 18 normalized photos from the operator's latest iCloud batch now detect and
generate complete crops locally: nine morning tables with 31 rows and nine
afternoon tables with 36 rows. Eleven of those photos were blocked by grid-5.
`validation/fuzzy-rows-photos.json` records the per-photo results. This validation
used temporary data and made no OCR requests; it does not measure count accuracy.
`validation/fuzzy_rows_check.py` reproduces the check from downloaded source PNGs
and their API metadata without changing the operator database.

Regression checks include residual slant from imprecise corner clicks, generous
padding, bowed/uneven rows, faint separators, preserved time ordering, missing
regions, and retries that keep previously saved manual corners. Results are in
`validation/fuzzy-row-results.xml`.
The full Windows run passed 152 tests with one skip; the subsequent saved-corner
retry checks also passed. The deployed Linux image passed 25 focused row and
corner tests. The rebuilt web and worker services are healthy and automatically
retry unresolved failures from the previous detector, retaining manual corners.

## Automatic table boxes and batch/ZIP picker — October 15, 2026

Perspective table detection now validates observed columns and count rows before
queuing OCR. The consented reference photo is detected without corner clicks and
produces all 31 morning rows. Synthetic checks cover morning, afternoon, full-day,
two separate tables, inset headings, perspective distortion, and rejection of
incomplete grids. Multi-file and nested ZIP uploads preserve independent source
images and boxes, while corrupt members remain isolated as source issues.

Batch photo-layout selection is saved before automatic reading, and individual
manual overrides survive redetection. Tests cover existing-database upgrades,
concurrent manual changes during detection, and the one-time retry of old
unresolved detector failures without resuming a paused batch.

`validation/corner_browser_check.py` passed in real Chromium at 1100px and 390px.
It verifies four-click saving, rejection/retry, coordinate scaling, switching ZIP
members, retaining partial selections through polling, saves to the selected
source, visible saved outlines, and late image-load responses. These browser
checks use local mock status responses and no operator data or OCR service.

Full regression results are in `validation/auto-box-results.xml`. Docker Desktop
was not running during this change; no live deployment or new model inference
was performed.

## iCloud JPEG/MPO and Live Photo ZIP import

The supplied iCloud Photos ZIP contains 18 JPEG/MPO photos and 11 MOV video
companions. The importer now selects each MPO's primary image, applies its EXIF
orientation, and skips MOV files before creating sources. The actual ZIP imports
all 18 photos with zero invalid-source issues and no video sources. Results are
in `validation/icloud-import-results.json`.

Regression tests cover distinct primary/auxiliary frames, EXIF rotation, pixel
limits, mixed ZIPs, deduplication, MOV-only selections, and unsafe MOV paths.
Existing path/symlink checks still apply before skipping a ZIP entry. Container
test results are in `validation/icloud-linux-results.xml`.

The image was rebuilt and both Compose services restarted. All 18 previously
rejected sources in the operator's existing batch were recovered from their
unchanged originals; invalid-source issues were resolved and the recovery was
audited. The browser can display the recovered photos for corner selection.

## Live Docker deployment and import

Started Docker Desktop and rebuilt/deployed the current app with Compose. Both
web and worker report healthy. Container diagnostics reach the configured LAN
Ollama 0.40.3 endpoint and confirm vision support for qwen3.5-hermes:64k.

A real Chromium browser uploaded the Fall workbook and the labelled reference
photo, marked its corners, waited for four successful OCR requests, and downloaded
the new monthly workbook. The manually checked first row is Public 0, External
blank, Internal 32, Dry 2, with all four fields accepted. The generated October
entry sheet contains these values at D564:G564 and October 9 at G562. There are
no source/cell issues; the test remains a draft because other dates lack photos.
Desktop and mobile report pages have no browser script errors. Results,
download, and screenshots are under `validation/docker-smoke-*` and
`validation/screenshots/docker-live-import*`.

The live check exposed a race: an old automatic geometry failure could commit
after a browser corner save and put the newer source version back into review.
Worker failure handling now updates only its original pending source version;
successful preprocessing also verifies the version/state before committing
pages and tasks. Two deterministic regression tests exercise both interleavings.
The corrected image is deployed and the same live test batch completes.

The full Linux-container regression results are in
`validation/docker-linux-results.xml`. Live OCR validates the old reference photo;
new-format crop mapping is covered by synthetic grids. Neither a full-sheet
accuracy rate nor Excel's own rendering/recalculation is claimed.

## Monthly Fall 2026 layout and corner matching

Legacy daily workbooks and the supplied Fall 2026 workbook now export to the
monthly BLANK layout. Old User Group + Coaches becomes Internal; External stays
blank for legacy photos. Tests cover separate External/Internal/Dry values,
all 67 time slots, new-month resets, continuation of counts and notes, leap-year
dates, blank versus zero, selected-month imports, and retention of the actual
Fall workbook's other months, summaries, styles and original BLANK. The fallback
asset contains only sanitized BLANK content. Existing settled batches queue one
new export on restart, retaining historical files without repeating OCR.

The real photo's full preprocessing passes with all four corners moved inward
or outward by up to eight pixels horizontally and vertically. Synthetic legacy,
new printed, and full-day monthly grids verify the cropped column mapping.
Printed layouts require manual corner/layout selection because their identical
column count cannot distinguish legacy User Group from new External/Internal.

A headless Chromium check at 1100px and 390px verifies scaled click coordinates,
retention of a partial selection across the five-second polling cycle, rejected
corner reset/retry, and automatic save after four clicks. It serves local mocked
APIs and never touches operator counts or the OCR server. Run it with:

```powershell
.\.venv\Scripts\python.exe validation/corner_browser_check.py C:\path\to\chrome.exe
```

The browser validation needs `websocket-client` in addition to the app's pinned
dependencies. Automated results are in `validation/monthly-layout-results.xml`
and `validation/monthly-corners-results.xml`. Excel rendering/recalculation and
live OCR on new-format handwritten photos have not been run.

The sections below record previous validation runs.

## Main-page steps, copy-down and likely blanks

The main import page now uses the same numbered sections as the report page:
choose month, workbook, photos, and start. The operator also approved arrows and
quotation/ditto marks as copy-down instructions and likely blank cells as blanks.
These supersede the original plan's arrow/ditto review policy.

Copy-down is calculated locally in date/time order, not by asking the model to
guess prior crop values. It copies exactly the preceding schedule slot in the
same date and column, including zero and blank. Chains across bands/photos are
resolved after reconciliation; edits above update unreviewed dependent cells.
Reviewed overrides remain protected. Missing or conflicting predecessors still
require correction. Carry provenance records the preceding cell key and preserves
the source mark. Likely blank text/status normalizes to an accepted blank, never
numeric zero. Unreadable numeric ink remains distinct.

55 focused checks passed, including mark recognition, likely blanks, cross-band
chains, reverse upload order, missing slots, blank/zero copying, correction
propagation, and the numbered home page. See `validation/carry-final-results.xml`.
Saved readings in settled batches were refreshed without inference; original
files, reviews and historical exports were preserved. A consistent pre-update
database snapshot is in `/data/snapshots/`.

## Simplified report page

The operator requested a four-step workflow. The page now displays only corner
marking, progress, images needing correction, and the latest download. Corners
save after the fourth click; page section is detected from the grid row count.
Image fixes are grouped with simple count/blank controls. Technical evidence,
all-cell lists, settings links, history, and batch-management controls are absent
from this page. Existing durable evidence/API functionality is retained.

Three focused route/geometry tests passed. A headless Chromium check exercised
four corner clicks and automatic saving, grouped per-image corrections including
blank versus zero, one latest download with the clean filename, and mobile
rendering. Job write APIs were mocked for the browser test, so it did not modify
operator counts. No browser page errors occurred. Screenshots are under
`validation/screenshots/`. Downloads of existing files are renamed through the
HTTP response; original artifacts are preserved. New export artifact names also
omit `needs-review`.

## Updated rough OCR profile

The operator requested approximate counts, no thinking, fewer checks, and numeric
letter substitutions. Live defaults are now `THINK=false`, `ROUGH_COUNTS=true`,
`VERIFICATION=off`, `NUM_CTX=8192`, `NUM_PREDICT=4096`, `ROWS_PER_BAND=12`.
Compact OCR returns numbers/addition text; the application derives count kinds
and terms. Morning pages need four requests instead of 19. Raw evidence, manual
decisions, blanks, exact time placement, and durable checkpoints are retained.
Letter substitutions apply only to complete numeric/addition expressions:
O/Q/D→0, I/L/l/|→1, Z→2, S→5, G→6, B→8 (lowercase variants where configured).

42 focused tests passed for substitution, single-pass reconciliation, crop counts,
streaming, and strict-mode compatibility. The final compact-number variant passed
all 19 fast-count tests. Evidence is in `validation/fast-count-results.xml` and
`validation/fast-count-final-results.xml`. The legacy test fixture explicitly
selects the original strict settings; fast-mode tests select the new settings.

A real six-row crop took 4.77 seconds with thinking disabled. The first row
produced 0 / 30+2 / 2. See `validation/evidence/fast-ocr/benchmark.json` and raw
stream evidence. This is a single-crop measurement, not a month throughput promise.
The earlier thinking benchmark used different crop sizes and should not be used
as a controlled speed ratio.

The final twelve-row crop completed in 8.54 seconds and emitted zero thinking
characters. Its complete JSON and stream are saved as
`validation/evidence/fast-ocr/twelve-rows-benchmark.json` and `twelve-rows.ndjson`.

The existing live batch was refreshed from saved A readings without inference.
Unresolved issues fell from nine to three; only the three 12:00 arrow cells remain.
Export revision 13 was generated automatically. Previously reviewed decisions
and earlier export versions remain available. A consistent database snapshot was
saved under the persistent volume's `/data/snapshots/` before refreshing.

The earlier strict validation/calibration results below describe the original
profile, which has been superseded for normal use by the operator's preferences.

## Workbook upload regression fix

The user's template with its sample daily sheet removed has MASTER formulas
`=IFERROR(AVERAGE('Boundary B'!C10),"")`. The initial validator wrongly required
a two-sheet range and rejected that empty-template form. Validation now accepts
both forms, checks the exact cell anchor, and expands the reference to the
generated month during export. The actual uploaded workbook is preserved in
`validation/regression/boundary-only-template.xlsx` and used for regression
coverage. The web upload test passed with this workbook; generated daily dates,
MASTER endpoint, zero placement, logos and printer parts are also checked.
Results: `validation/master-fix-results.xml` and
`validation/master-upload-results.xml`.

Source, UI, durable web/worker services, deployment, and recovery instructions are
implemented. The running app is at <http://localhost:8000> with a persistent
Docker volume. Original workbook and photo were preserved byte-for-byte.

## Automated checks

44 distinct tests are covered across the Linux suite and the additional
continuation check. The final targeted crash check passed after fixing a cold
startup allowance. The original suite report retains that timing failure;
reports have not been edited to conceal failed runs.

| Run | Actual result | Evidence |
| --- | --- | --- |
| Initial workbook milestone, Windows | 2 passed | All time anchors, leap year, blanks/zero, ordering, exact unrelated XML, drawing/logo/printer bytes, MASTER endpoints |
| Windows ingestion/schema/stream/UI checks | 27 passed; one test-client deprecation warning | Decode/dedup/ZIP security, addition grammar, streaming failures, read/wall deadlines, UI routes |
| Windows final workbook/stream/resource checks | 13 passed | `validation-changes.xml` |
| Windows review/export checks | 18 passed; one deprecation warning | `validation-review.xml` |
| Actual killed worker, Windows | 1 passed | `validation-crash.xml` |
| Linux container full suite | 42 passed, 1 startup-wait failure | `validation/linux-results.xml` |
| Linux corrected killed-worker check | 1 passed | `validation/linux-crash-results.xml` |
| Linux continuation plus actual photo geometry | 2 passed | `validation/continuation-results.xml` |
| Pinned dependencies, Windows and Linux | `pip check`: no broken requirements | Installed set in `requirements.lock` |
| Docker build and Compose config | Successful | Python 3.14 Linux image, Docker Engine 29.4.2 |
| Live web and connection | HTTP 200; Ollama diagnostic successful | `/health`, `/api/settings/diagnostics` |
| JavaScript syntax | `node --check` passed | `app/static/app.js` |

The full container suite's 15-second startup allowance was too short while the
machine was building/running other containers. The corrected test allows up to
60 seconds, captures child diagnostics, then kills the real worker process
mid-request. It verifies abandoned attempts become interrupted and unfinished
tasks return to retry_wait. Windows launches the actual interpreter for this
test because its venv launcher otherwise leaves a child interpreter alive.

The mock endurance run uses 62 source records with morning and afternoon slots,
plus an intentionally corrupt image. It makes 124 sequential successful requests,
restarts the worker after 20 checkpoints, retains all succeeded tasks, merges
same-slot observations without adding them, and automatically exports a draft.
This is synthetic queue/endurance coverage, not 62 photographed sheets or a real
GPU month benchmark. Other tests cover outages/circuit recovery, malformed and
truncated output, exclusive ownership, interrupted requests, pauses, conflicting
photos/terms, reviewed-cell protection, date-only correction, export failures,
edits during export, recalculation-engine failure, and consistent SQLite backup.

Linux pytest initially warned that its read-only app directory could not store
pytest's optional cache. The targeted rerun uses `/tmp/pytest-cache`. The
Starlette/httpx TestClient deprecation warning affects test tooling; requests
and production app checks passed.

## Real Ollama benchmark

Endpoint: `http://192.168.68.151:11434`. Observed Ollama version: `0.35.0`.
Exact model: `qwen3.5-hermes:64k`, digest
`b7b9afeaf023a549a9e6fc7960694f3c32fc490d415bbdf1751e2f390cf4ae48`.
The API advertises vision and thinking. Four sequential calls per run used fresh
contexts, boolean thinking enabled, 16K context, temperature 0.1, presence penalty
0, output budget 8192, and keep-alive 30m.

Initial header crops included numerical rows; both header calls ended with
`done_reason=length` at 8192 output tokens and were rejected. The implementation
now isolates the header and uses a simpler header schema/prompt.

| Corrected run | Result | Server duration |
| --- | --- | --- |
| Header A | October 9, 2026; clear | 17.53 s |
| Header B, alternate framing | October 9, 2026; clear | 12.29 s |
| Count A, first row | Public 0, Group `30 + 2`, Dry 2; matches manually checked subset | 21.24 s |
| Count B, two-row alternate band | Invalid numeric raw text `O`; strict validation rejected the entire pass | No accepted readings |

The application computes `30 + 2 = 32` locally. A single successful count pass
does not meet automatic acceptance: the failed B pass prevents agreement.
No whole-sheet or percentage accuracy claim is made. The supplied photo has
crossed-out counts and arrows that require human review.

Saved evidence: `validation/evidence/initial-calibration.json`,
`corrected-calibration.json`, header/A JSON, and `ollama-ps.json`. Full raw streams
are retained locally under `calibration-output/` and excluded from the source
archive. The model API reported size and size_vram of 6,014,380,276 bytes at a
16K context in the captured ps observation; this is a point-in-time API report,
not a guarantee of hardware residency or available memory for future requests.

The photo's perspective was rejected by conservative automatic grid detection.
The manually inspected corners produce verified 31 morning rows, eight column
boundaries, deterministic crops, and saved perspective transforms. No coordinates
were guessed when automatic geometry failed.

## Workbook evidence and remaining validation

The fixture original SHA-256 is
`31cfa3e66840953b98c58b895bcecafc3cb8f481bd4c4d256e26e2b13ac8bff4`.
The copied photo SHA-256 is
`28b495b9edc0759c228a56367be5b9a73ea745ff95f525b6fe50703fcd6526ea`.

`validation/examples/synthetic-october-needs-review.xlsx` is explicitly synthetic.
It demonstrates boundary-time placement and template fidelity, and must not be
treated as recognized photo data. XLSX ZIP integrity and accepted-cell readback
were checked. Entire unrelated daily worksheet XML, image/drawing bytes and
printer-setting bytes are compared against the actual original fixture.

Excel/LibreOffice were unavailable for visual print comparison and independent
formula-engine recalculation. Formula text, blank/zero semantics and independent
expected averages are tested; cached MASTER values remain unverified. The
optional LibreOffice stage preserves the original artifact on failure and has
failure-path coverage, but its successful engine path is untested here.

Still needed for operational calibration: 10–20 diverse manually checked sheets,
thinking on/off and context comparisons, exact numeric/blank/row/date metrics,
review workload and missed-error measurements, and a representative real
month-sized batch on the operator's hardware. Use review and spot checks until
those measurements support a production accuracy claim.
