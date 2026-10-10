# Pool Headcount

A local FastAPI application and separate durable worker for monthly handwritten
pool counts. Uses your existing `qwen3.5-hermes:64k` Ollama model directly.
Originals, attempts, reviews, and export revisions are kept in SQLite and `/data`.

The default is now **rough headcount OCR**: no thinking, one extraction pass,
12 rows per band, 8K context and short count-only responses. A morning page needs
four requests (one date header and three bands), instead of the original 19.
Count text substitutes O/Q/D → 0, I/L/l/| → 1, Z → 2, S → 5, G → 6, B → 8.
Raw text is preserved. Addition is computed locally; blank cells stay blank.
Arrows and quotation/ditto marks copy the immediately preceding time slot in the
same date and column. This works across crop bands and propagates subsequent
corrections. A preceding blank copies as blank; an unavailable preceding cell
requires review. Quite likely blank readings are also accepted as blank.
Readable corrections are accepted as rough counts; unreadable cells and
conflicting photos still appear for review. These defaults reflect the operator's
updated preference for speed and approximate counts over independent verification.
`THINK=false`, `ROUGH_COUNTS=true`, `VERIFICATION=off`, `ROWS_PER_BAND=12`.
To apply these rules to an already processed batch without OCR, use
`python -m app.cli refresh JOB_ID`. Reviewed decisions are retained.

The main page has four steps: choose the month, add the workbook, add photos,
and start the import. The batch page has four steps: mark table corners, track progress, fix flagged
images, then download the latest workbook. Four corner clicks save automatically;
morning/afternoon is detected from the row count. Image corrections are grouped
under each photo and automatically regenerate the workbook. Only the latest
download is shown. Download names are `YYYY-MM-headcounts.xlsx`; revision history
and detailed evidence remain stored and accessible through the CLI/API.

## Install on Windows

Python 3.14 was used for the pinned dependency set. From this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m app.cli migrate
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the worker in a second terminal:

```powershell
.\.venv\Scripts\python.exe -m app.worker
```

Open <http://localhost:8000>. `.env` already has the supplied LAN address;
change `OLLAMA_BASE_URL` if needed. Web and worker must use the same `DATA_DIR`.
An environment variable overrides `.env`. Restart both processes after changes.
No counts run through a cloud service. No Ollama model or global options are changed.

After installation, `powershell -ExecutionPolicy Bypass -File .\start.ps1` starts
both processes in hidden windows. Pause in the app and wait for the current
request to finish before `powershell -ExecutionPolicy Bypass -File .\stop.ps1`.
Forced shutdowns remain recoverable.

Linux equivalents:

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.lock
cp .env.example .env
.venv/bin/python -m app.cli migrate
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# In another terminal
.venv/bin/python -m app.worker
```

## Docker Compose

Start Docker Desktop (Linux containers) or the Linux Docker engine first:

```sh
cp .env.example .env
docker compose build
docker compose run --rm web python -m app.cli migrate
docker compose up -d
docker compose logs -f worker
```

The two CPU application services share `pool-data`. No Ollama service is deployed.
Health checks use HTTP for web and the worker's independent heartbeat. Only one
worker can own this directory, enforced by an OS file lock and DB owner record.
Keep SQLite on a local disk, never SMB/NFS. Container persistence lives in the
named volume; stopping/recreating containers retains it. Do not use `down -v`
unless you intend to destroy the volume. Docker build, both service health checks,
persistent-volume migration, container recreation, and LAN connection diagnostics
were validated after starting the Docker engine.

## Use

1. Create a batch with month, workbook, photos/ZIP, and explicit workbook mode.
   New-month replaces sample daily sheets; continuation retains that month's
   existing inputs and raises conflicts against new observations. Continuation
   refuses a different month. Unsupported/corrupt photos appear as issues.
2. The upload commits files and records before returning. Closing the browser
   has no effect on the worker. Hash-identical uploads are deduplicated.
3. In **Step 1**, click around
   **all seven columns, count rows only**, in top-left, top-right, bottom-right,
   bottom-left order. Exclude the column header. The fourth click saves the
   selection and detects morning/afternoon automatically.
   The original is kept; a high-resolution rectified table and transform are saved.
   For a photo containing both sections, the source configuration API accepts
   two geometry objects. Use the API example below until both-table editing is
   supported in the visual corner picker.
4. The default single pass reads counts and blanks with short responses. Numeric
   OCR letter substitutions and readable corrections are accepted automatically.
   Time/date placement is checked. Unreadable cells and conflicting sources go to
   review. Blank and numeric zero are separate actions. Accepted cells can be
   inspected/corrected. Optional `ROUGH_COUNTS=false`, `VERIFICATION=always`
   restores detailed readings and independent B crops for stricter checking.
5. Resolve issues and acknowledge missing days/sections as no source or not
   applicable. Counts are never fabricated for these periods. Source issues can
   be acknowledged as unusable evidence; this is recorded in the audit trail.
6. A monthly XLSX is generated automatically when work settles. Unresolved cells
   are blank and listed in the report. Review changes generate a new immutable
   revision without inference. Step 4 shows the latest download. Earlier versions
   remain stored in export history, accessible through the CLI/API.

For the supplied photo, automatic grid detection conservatively rejects its
perspective. Verified normalized corners for its morning count table are
`[[154,262],[918,252],[968,1185],[138,1200]]`; date is October 9, 2026.
These coordinates apply only to the supplied 1080 × 1440 re-downloaded fixture.

The app binds to localhost by default and has no user accounts. To expose it to
a LAN, put it behind your access-controlled reverse proxy. Set an explicit
upload body size limit matching your batch limit; upload failures can be retried
by adding the same files to the job. Avoid routing Ollama inference through an
HTTP proxy with short response timeouts. Use the direct LAN address for backend
requests. The app rejects browser writes from a different origin.

## CLI and API

```sh
python -m app.cli import-month --month 2026-10 --template "Head Counts.xlsx" --photos /path/to/photos --mode new-month
python -m app.cli status JOB_ID
python -m app.cli pause JOB_ID
python -m app.cli resume JOB_ID
python -m app.cli retry JOB_ID
python -m app.cli coverage JOB_ID
python -m app.cli export JOB_ID
python -m app.cli add JOB_ID /path/to/more-photos.zip
python -m app.cli diagnostics
```

Folder and ZIP ingestion share the same service as web uploads. The API is
documented at `/docs`. To assign two tables, POST to
`/api/jobs/JOB_ID/sources/SOURCE_ID`:

```json
{"date":"2026-10-09","confirm":false,"reviewer":"William","geometry":[
  {"section":"morning","corners":[[10,10],[900,10],[900,600],[10,600]]},
  {"section":"afternoon","corners":[[10,700],[900,700],[900,1400],[10,1400]]}
]}
```

Use actual normalized-image coordinates. Date-only assignment reuses successful
readings. `confirm:true` explicitly acknowledges contradictory recognized dates
and is audited. Reprocess is explicit and creates a new version; reviewed cells
are protected and new evidence is flagged. Adding a replacement photo retains
the old photo and resolves conflicting observations per cell in review.

## Outages, pauses, and recovery

Jobs: ingesting → queued → running → completed / completed_with_issues. Outages move jobs to
waiting_for_ollama; actionable model/configuration errors pause them. Pause/cancel
stop dispatch after the active call and preserve evidence. Resume reopens work.
Review/added sources advance the revision and reopen the batch. Export failures
use awaiting_review with a diagnostic and can be retried independently.

Tasks: pending → in_flight → succeeded; transient failures → retry_wait;
exhausted content/resource failures → failed. Split retries supersede the parent
and create smaller child bands. Source needs_review means geometry/date needs
human input; deferred means exhausted tasks. Successful task keys are preserved.

SQLite transactions never span a model request. Completed response/readings are
committed together. On restart, previous in_flight attempts become interrupted
and only unfinished tasks retry after a cooldown. Streaming cannot be resumed.
After five availability failures a circuit breaker uses short health checks;
availability does not consume content-retry budgets. Content retries get three
attempts, then smaller bands / a larger output budget. Resource errors get an
8K context and smaller-band attempt, then defer. Permanent HTTP errors pause.

HTTPX read timeout is silence between chunks (default one hour), independently
bounded by a four-hour wall watchdog (`WALL_TIMEOUT=0` disables it). The client
response is closed before releasing the inference slot. A disconnected remote
generation may still run; health is not proof it ended. Cooldown is configurable.
Other Hermes/Ollama clients may contend for the GPU. Optional `PAUSE_START` and
`PAUSE_END` (`HH:MM`, process local time) reserve a daily window; manual pause is
available too. The app does not stop shared models or change server parallelism.

Worker logs rotate at 5 MB with four backups. Every attempt's raw content and
thinking stream is bounded by `MAX_RESPONSE_BYTES` (default 20 MB). Hitting the
bound requires retry/review, never acceptance. Original files and reviews are
never automatically deleted. Set file-count/expanded/pixel limits in `.env`.

## Workbook fidelity and recalculation

openpyxl reads/validates the workbook. A narrowly scoped OOXML writer preserves
the original image/drawing/printer parts, styles, merged ranges, formulas, row
sizes, page setup and print layout. Daily sheets clone BLANK XML and immutable
relationships. Only E3 and requested C/D/E anchors are written. MASTER's daily
range start is updated; it remains a 3-D **average**, not attendance total.
IMPORT REPORT is after hidden Boundary B, outside all summary ranges.

An empty template may have MASTER formulas referencing only `'Boundary B'` after
the example daily sheet is deleted. This is supported: export expands that
reference to the generated month's first daily sheet through Boundary B. Wrong
cell references, sums, and different IFERROR fallbacks are rejected explicitly.

All exports request recalculation on open. **Cached MASTER values are not
calculated by Python**. Independent expected averages appear in the report.
Optional `LIBREOFFICE` enables an isolated headless profile/output directory;
the recalculation button/CLI preserves the original export and checks cached
3-D averages before exposing a separate recalculated copy. LibreOffice was not
installed here, so actual recalculation and rendering in Excel remain unverified.

## Backup and restore

Pause each batch, wait for its current request to checkpoint, then:

```sh
python -m app.cli backup /path/outside/data/backup-2026-10-10
```

This uses SQLite's consistent backup API, then copies all referenced immutable
templates, originals, normalized images, crops, responses, and exports. An active
partial stream is not stable; pausing first is recommended. Preserve the backup
as a unit. For a container volume, run the same command with a mounted backup
directory using `docker compose run --rm -v /host/backups:/backups web ...`.

To restore, stop both processes, copy backup contents into a fresh data directory,
and use the same absolute data path as the original deployment (recorded in
`restore.json`). Moving to a different path requires rewriting stored artifact
paths in jobs/sources/pages/tasks/attempts/exports and recalculated report metadata;
do that on a copy and validate it before starting the worker. Never mix a restored
database with a newer set of inputs. The next worker recovers abandoned tasks.

## Validation and calibration

```sh
python -m pytest -q
python -m app.calibration --output calibration-output
```

See [VALIDATION.md](VALIDATION.md) for measured results and remaining limits.
The fixture workbook/photo are local consented copies; the originals in Downloads
are untouched. Calibration sends crops only to the configured Ollama LAN server.
The small built-in benchmark checks the date and first row only. It must not be
used to claim monthly accuracy. Gather 10–20 manually checked diverse sheets and
compare profiles at 8K/16K/32K and thinking on/off; measure exact numeric and
blank/zero accuracy, row/date errors, review workload, and missed autoaccepted
errors. Record `ollama ps` residency and timing/token metrics. No hardware speed
or accuracy percentage is promised.

API references checked during implementation:
[Ollama chat](https://docs.ollama.com/api/chat),
[HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/),
[openpyxl copying limitations](https://openpyxl.readthedocs.io/en/stable/tutorial.html).
