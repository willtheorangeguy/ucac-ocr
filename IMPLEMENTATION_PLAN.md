# Pool headcount photo importer — Codex implementation plan

> Historical design specification. Current operating instructions live in [docs/README.md](docs/README.md). Later operator decisions supersede the original strict OCR, copy-down, and daily-sheet export policies; see [count and workbook rules](docs/rules.md).

## Build brief

Build a local, self-hosted application that accepts an entire month's pool headcount photos, processes them sequentially through an existing remote Ollama server, and produces one monthly XLSX using the supplied workbook's layout and MASTER calculations.

Accuracy, durable progress, and eventual completion take priority over speed. The model runs on an NVIDIA GTX 1080 Ti. A slow response is normal. Closing a browser, restarting a container, losing an Ollama connection, or retrying one image must not discard completed work or require starting the month again.

Implement the application described below. This document is the specification; do not build only a demo, synchronous upload handler, or script that keeps its results solely in memory. Deliver source code, Docker Compose, configuration examples, automated tests, and installation/recovery instructions. Use incremental milestones and report actual validation results. Do not claim model accuracy until measured on manually checked photos.

### Supplied reference files

- `Head Counts.xlsx`: original workbook/template. The user will give this file to Codex alongside this plan.
- `IMG_6761B643-419F-400C-B407-B3F54D616E10.jpeg`: handwritten morning example dated October 9, 2026.
- Preserve both originals. Include consented copies as local test fixtures; no external uploads or cloud inference are necessary.
- The Ollama URL is not supplied. Make it configurable rather than blocking implementation. Do not assume `nas-ai` resolves inside every container.

### Confirmed model

Use the exact installed name `qwen3.5-hermes:64k`.

Observed configuration: architecture `qwen35`, approximately 9.7B parameters, `Q4_K_M`, supported context 262,144, configured `num_ctx=65536`, minimum model requirement Ollama 0.17.1. Capabilities include vision and thinking, with boolean thinking modes. Existing defaults include temperature 1 and presence penalty 1.5.

The application calls Ollama directly. Hermes Agent is not part of the processing pipeline. Do not edit/recreate the model, restart Ollama automatically, or change its global settings.

## 1. Required behavior and boundaries

1. Upload multiple images in one batch for a selected year/month. Support JPEG, PNG, and WebP initially; provide ZIP/folder ingestion using the same ingestion service. Validate actual decoded files, ZIP paths, and configurable expanded size/file-count limits. List unsupported formats clearly. HEIC/PDF support can be a later addition.
2. Keep one inference request active at a time across all application jobs and both extraction passes. Finish an image's eligible work before moving to the next image; defer a persistently problematic image so it cannot block every later image.
3. Extract only date, time, Public Patrons, User Group + Coaches, and Dry / Spectators. Completely ignore Men's CR Check, Women's CR Check, and Staff Initials.
4. Preserve a genuinely blank count as `null` and export it as an empty Excel cell. A handwritten zero is numeric `0`.
5. Evaluate summations locally: `30 + 2` becomes numeric `32`. Keep original text in the audit data. Support chains of nonnegative integer additions; reject other expressions. Never use `eval()` or execute model output.
6. Crossed-out, overwritten, unreadable, or ambiguous entries require review. Arrows/ditto marks have no agreed interpretation: flag them and do not silently carry values forward or turn them into zero.
7. Multiple photos can represent one date, such as morning and afternoon pages. Merge by date/time/column; never add duplicate observations of the same time slot together.
8. Finish processing all possible images despite individual corrupt files or exhausted content retries. Export one workbook automatically after processing settles, clearly labeled as needing review if unresolved issues remain. Once issues are resolved, regenerate the final workbook without repeating inference.
9. All accepted cells have source-image provenance. Missing data must never be reported as a measured zero or as successfully recognized handwriting.

## 2. Application architecture

Use Python with FastAPI, server-rendered Jinja templates and lightweight JavaScript, Pydantic schemas, HTTPX, Pillow, OpenCV, SQLite, and a workbook adapter. Use openpyxl for the initial workbook implementation only with the fidelity requirements in section 8. Pin a tested dependency set during implementation; do not invent unverified version combinations.

Run two services/processes from the same image:

- **Web:** uploads, job status, previews/review, settings, export downloads; no inference in HTTP handlers.
- **Worker:** durable queue consumption, preprocessing, streamed Ollama calls, validation, retries, reconciliation, and export triggering.

Use a shared persistent `/data` volume for inputs, images/crops, the SQLite database, attempts, and generated artifacts. The web service commits uploads before returning a job ID. The worker does not depend on the browser staying connected. Polling status is sufficient; avoid requiring a persistent browser connection for job execution.

Use one worker replica, one process-level lock, and a database inference-owner record. Prevent accidental second workers from sending parallel inference. Run schema migrations explicitly and use short database transactions; never hold a SQLite write transaction during an Ollama call. Keep SQLite on a local filesystem, not an SMB/NFS share. Large image/export storage can use a separately configured path, but database and checkpoint semantics must remain reliable.

Suggested modules:

```text
app/
  config.py, main.py, cli.py
  db.py, migrations/
  ingestion.py, preprocessing.py, layout.py
  schemas.py, prompts.py, ollama_client.py
  worker.py, recovery.py, reconciliation.py
  workbook.py, validation.py
  routes/, templates/, static/
tests/
  fixtures/, unit/, integration/
Dockerfile
compose.yaml
.env.example
README.md
```

## 3. Persistent jobs, checkpoints, and restart recovery

Persist these entities: jobs, source images, detected pages/tables, crop tasks, inference attempts, per-pass cell readings, canonical cells, review issues/decisions, and export versions.

Record at least: job UUID, requested month, immutable template hash, source SHA-256, original filename, assigned/observed date, page section, task key, model name/digest if available, prompt/schema/preprocessing versions, effective inference options, attempt timestamps, response status, raw response location, and normalized results.

Suggested job states: `queued`, `running`, `paused`, `waiting_for_ollama`, `awaiting_review`, `exporting`, `completed`, `completed_with_issues`, and `cancelled`. Per-task states distinguish `pending`, `in_flight`, `retry_wait`, `succeeded`, `needs_review`, and `failed`. Document permitted transitions; do not use one vague `done` flag for every outcome.

Checkpoint after ingestion, preprocessing, every completed inference task, reconciliation, each review decision, and export. Each checkpoint is transactional. Commit the successful response and its validated readings together. Write files to temporary paths and atomically rename them before committing their references.

On restart, detect abandoned `in_flight` tasks from the previous worker generation and mark their attempts interrupted. Retain validated completed tasks and any partial response logs; retry the smallest unfinished crop/pass. Do not pretend token streaming can resume an interrupted model generation: the incomplete request must be rerun.

Hash-identical uploads are deduplicated within a job. Hashes alone do not detect different photos of the same sheet; reconcile those separately by their date and time slots. Completed task keys include input hash and processing configuration. An explicit reprocess action creates a new extraction version; it never silently replaces reviewed decisions.

Pause means stop after the active request and checkpoint. Cancel stops new work and preserves evidence; it does not delete the job. Restart recovery also applies if a process is killed before a graceful pause. Review/export operate on immutable result revisions, so a new edit cannot be lost behind a stale export.

## 4. Timeouts, outages, and retry design

These are proposed starting defaults, not measured performance limits:

| Setting | Starting value | Meaning |
| --- | --- | --- |
| Inference concurrency | 1 | Application-wide, including retries and verification |
| Connect timeout | 15 seconds | Establish the Ollama connection |
| Write timeout | 300 seconds | Send a potentially large encoded crop |
| Pool timeout | 30 seconds | Obtain a client connection |
| Read inactivity timeout | 3,600 seconds | Maximum silence between received chunks, including the first response chunk |
| Request wall-time limit | 14,400 seconds | Optional four-hour bound for one request; configurable/disableable |
| Batch deadline | None | A month may run overnight or for several days |
| Retry delays | 30, 120, 300, 900, 1,800 seconds | Exponential-style delay with jitter |
| Heartbeat interval | 10 seconds | Worker liveness, separate from model activity |

Use `stream=true` on `/api/chat` and consume the stream in the backend. Assemble only `message.content` for the extraction JSON; preserve thinking separately when supplied. Record arrival times and the final `done`/`done_reason` and metrics. Require a completed stream and valid result before accepting readings. Disconnects, token-limit completion, errors, or incomplete JSON are not successful extractions.

Streaming does not guarantee early chunks: loading, queued requests, and prompt/image evaluation can be silent for a long time. A HTTPX read timeout is an inactivity timeout, not a total-job deadline. Implement the independent wall-time watchdog explicitly and test cancellation behavior.

Retry policy:

- **Unavailable server, disconnect, timeout, 429/503, transient 5xx:** retain the task and retry with backoff. After five consecutive availability failures, use a circuit-breaker state and inexpensive periodic health checks with fresh attempts after recovery. An extended outage does not permanently fail the entire month or consume content-retry budgets.
- **Invalid JSON, schema mismatch, truncated generation:** retain the attempt; allow up to three content attempts, then smaller crops/larger output budget where appropriate. Never ask another model to invent missing JSON fields from an incomplete response.
- **Ambiguous handwriting:** use targeted rereading/verification, then review. Endless retries do not make unclear ink reliable.
- **Invalid/corrupt source:** create a visible issue and continue other images.
- **Model missing, no vision support, unsupported options, invalid endpoint, authentication failure:** pause with a clear actionable diagnostic. Do not retry these rapidly or automatically pull a different model.
- **OOM/resource error:** back off and try an explicitly recorded smaller-context/smaller-band profile. Preserve original image resolution. If still unsuccessful, defer/review rather than repeatedly overloading the GPU.

Always close/cancel the previous client request before releasing the inference slot. Ollama does not provide a durable client request ID that makes retries exactly-once; server-side work after a disconnect may be uncertain. Apply a configurable cooldown after uncertain disconnects and stop dispatching if the local request task cannot be terminated. Never retry while the previous local request remains active, and never automatically stop a shared Ollama model to force cancellation. Idempotent checkpoints prevent duplicate accepted data even if remote inference is repeated.

Health checks must be quick and independent of the long inference client. A healthy API or `ollama ps` is not proof a previous generation has finished. Other Hermes clients can still contend for the server; disclose this and offer optional scheduling/pause windows. Server-wide parallelism changes are documented as optional operator choices, not made by the app.

Progress shows elapsed time, latest worker heartbeat, latest inference chunk, current image/pass/band, attempts, completed images, deferred images, and issues. Show a rough ETA only after observed timings, with no fixed minutes-per-image promise.

## 5. Model request profile for the 1080 Ti

Configure all settings per request and save the effective profile with results:

```text
OLLAMA_MODEL=qwen3.5-hermes:64k
OLLAMA_BASE_URL=<operator-supplied URL>
INFERENCE_CONCURRENCY=1
NUM_CTX=16384
TEMPERATURE=0.1
PRESENCE_PENALTY=0
THINK=true
NUM_PREDICT=8192
KEEP_ALIVE=30m
ROWS_PER_BAND=6
VERIFICATION=always
```

These are initial engineering choices to benchmark. The 64K context setting may increase memory requirements without helping these small tasks. Start at 16K per request and test 8K/32K as needed; account for image tokens as well as text and output. Do not truncate a request silently. The GPU has limited memory and model weights, vision processing, cache, and other clients share it; do not promise full GPU residency. Record actual `ollama ps` observations and metrics in the calibration instructions.

Default to thinking enabled because speed is secondary; benchmark thinking disabled as an alternative. A truncated thinking response must trigger the same incomplete-result handling. Keep a sufficient configurable output budget. Low temperature is a starting hypothesis, not an accuracy guarantee. Select final settings using manually checked examples.

Use fresh chat context for every crop. Override any agent-specific system instructions with explicit extraction instructions; do not send Hermes tool definitions or conversation histories. Preflight `/api/show` and a small image request against the actual installed model/Ollama version. Verify image input, schema output, and boolean thinking controls, rather than assuming every client wrapper supports them identically.

## 6. Image preparation and row alignment

1. Preserve the uploaded original and normalize EXIF rotation. Decode errors become issues.
2. Detect the printed table using grid geometry and the known form. Correct perspective and deskew with saved coordinate transforms. Keep a high-resolution normalized image; do not aggressively shrink a whole page to a small thumbnail.
3. Classify morning versus afternoon from observed time labels. Detect multiple tables if both sections appear in one image. Verify detected row/column counts and geometry; a suspicious grid must not produce guessed cell coordinates.
4. Extract date/header separately. The morning reference has a date; some afternoon pages may not. For undated pages require an explicit date assignment or confirmed filename/paired-page association. Do not infer date merely from upload order. Conflicting printed/handwritten dates, filenames, selected month, or section labels create review issues.
5. Crop row bands containing the time labels and only the three numerical columns. Start with six rows per band. Use deterministic band IDs and allow overlap for alignment verification; deduplicate overlaps by canonical time/column keys.
6. Include the expected time list in each prompt. Compare observed row alignment against the fixed schedule. Missing rows must remain missing at their original positions; never shift all later observations up one row.
7. Keep original-color and optional enhanced versions. Never erase corrections or handwriting while removing grid lines. A preprocessing variant can assist rereading but must remain tied to original evidence.
8. If geometry fails, allow manual table corners/section/date assignment and reprocess. Model-only table localization can be a fallback with explicit validation, not an unverified source of row mapping.

## 7. Extraction, verification, and review

Use a strict JSON schema with exactly the expected rows/fields. Each field records:

```json
{
  "raw_text": "30 + 2",
  "kind": "sum",
  "terms": [30, 2],
  "ambiguous": false,
  "reason": null
}
```

Define `kind` as `blank`, `integer`, `sum`, or `unclear`; use nullable raw text/terms as appropriate. Canonical `value` is calculated by the application. Keep `blank`, `unclear`, and processing failure distinct even if all eventually export an empty cell in a provisional workbook.

Prompt requirements: read only visible ink, never infer a plausible count, distinguish zero from blank, preserve addition terms, flag correction marks/arrows, ignore unrelated columns, and return every expected row without inventing observations. Model instructions come from trusted templates, not text detected in the photo.

For every image run two passes sequentially:

- **A:** row-band extraction from the normalized table.
- **B:** independent verification from alternate crops, such as smaller bands/column strips with explicit time labels. Do not include pass A's answers in pass B's prompt. Verify blank cells too.

Reconcile date, row identity, blank/integer/sum status, individual terms, and computed value. Matching totals from different readings of the terms should still trigger review. Agreement by the same model is useful evidence, not proof of correctness; deterministic repeated calls on identical crops are not independent verification. Use a manual truth set and spot checks.

Accept clear agreeing readings automatically only when geometry, time coverage, schemas, and all checks pass. Flag disagreements, correction marks, unusual time/date assignments, duplicate source conflicts, and missing expected rows. Optional plausibility checks create warnings only; never replace counts with likely values. No invented numeric capacity threshold.

Review UI displays source crop, original photo access, both readings, computed sum, date/time/column, reason, and editable value. Explicit blank and zero actions must be separate. Save reviewer decisions immediately with an audit trail; lock reviewed cells against later automatic overwrites. Resolve conflicting photos per cell, not by summing or always choosing the newest file. Allow replacing a bad photo and rerunning only affected tasks.

## 8. Workbook writer and MASTER preservation

### Known workbook mapping

| Item | Location |
| --- | --- |
| Template | `BLANK` |
| Summary | `MASTER` |
| Existing example daily sheet | `September 9` (count inputs are empty in supplied example) |
| Hidden end marker | `Boundary B` |
| Daily date | `E3`, merged through `H4` |
| Times | Column B |
| Public Patrons / User Group + Coaches / Dry-Spectators | Columns C / D / E |
| Morning time anchors | Rows 10, 12, ..., 70: 05:15–12:45 |
| Afternoon time anchors | Rows 78, 80, ..., 148: 13:00–21:45 |
| Ignored fields | Columns F, G, H |
| Daily print area | B1:H149 |

Every count is written to the top-left anchor of its existing merged cell. Validate labels, time schedule, merges, and sheet roles against the uploaded template instead of silently assuming a changed workbook has the same layout. Cached time values may have floating-point drift: normalize to minute-of-day and verify unique matches. Leave time formulas untouched.

MASTER uses formulas such as `=IFERROR(AVERAGE('September 9:Boundary B'!C10),"")`. These are three-dimensional averages across matching daily cells, not sums, unique visitor counts, or daily attendance totals. Blank cells are ignored by AVERAGE; real zeros participate.

Default **new-month** mode:

1. Generate a copy from the supplied workbook; never overwrite its source.
2. Retain BLANK, MASTER, and Boundary B. Replace source sample daily sheets in the output copy with the selected month's date sheets. Do not import September example data into October averages. If an input workbook contains populated daily sheets, require the operator to choose new-month versus continuation mode at job creation.
3. Create one dated sheet for each calendar day in the selected month, in chronological order, between MASTER and Boundary B. Use readable names such as `October 9`; put the full typed date in E3. Missing-day sheets stay empty and are identified in the job/report. A day with no uploaded images is not automatically a confirmed closure or an all-zero day.
4. Preserve MASTER's formula structure and change only the daily-range start endpoint to the first generated daily tab. Keep Boundary B hidden and count-empty. All daily tabs lie inside this range.
5. Write only C/D/E approved numeric cells and E3. Ignored F/G/H inputs remain as in the blank template. Numeric sums go in as numbers, not literal strings.
6. If unresolved readings remain, generate a clearly named `needs-review.xlsx` with affected cells blank and visibly identified. Place an `IMPORT REPORT` tab after Boundary B, outside every MASTER range, listing unresolved cells, failed/deferred sources, missing days, and export revision. Do not silently conflate these issues with genuine observed blanks.
7. Generate the final monthly XLSX after all count/date/conflict issues are resolved. Missing-day coverage can be explicitly acknowledged as no source/not applicable without fabricating counts. Maintain final/draft distinction in both UI and report.

In **continuation** mode, preserve existing daily values, dates, formulas, and sheets. Import into matching dates with conflicts requiring review; a later upload must not overwrite existing numerical input without a recorded decision. Never expand a MASTER range across another month unnoticed.

### Template fidelity and recalculation

The supplied workbook contains a logo image/drawing and printer-setting parts. Blind `copy_worksheet()` is insufficient: openpyxl does not copy images/charts automatically. Build a tested template-copy helper that includes logo placement, merged ranges, styles, row/column sizes, time formulas, page breaks/setup/margins, print areas/names, and sheet visibility. Test import/save preservation against the actual reference. If openpyxl cannot preserve a required part, implement a narrowly scoped OOXML ZIP/XML preservation adapter rather than delivering a degraded template. Do not use private image APIs without a documented, tested encapsulated strategy.

Workbook libraries generally do not calculate Excel formulas. Preserve formulas, request recalculation on open, and provide an optional tested LibreOffice headless recalculation stage with an isolated profile/output directory. Verify three-dimensional averages, blanks versus zeros, cached values, and template fidelity after recalculation. A successful save or intact formula text is not recalculation proof.

If a recalculation engine is unavailable, keep valid formulas and explicitly indicate that cached MASTER results require opening in Excel/LibreOffice. Do not claim the downloadable preview is recalculated. Compute independent expected averages for validation/reporting; do not replace MASTER formulas with static numbers. Recalculation failure must preserve the already generated workbook and allow retrying only export.

Write exports atomically from a transactionally consistent accepted-data snapshot. Store a version/checksum and serialize exports per job. Retries regenerate from the original template and snapshot, not by incrementally patching a partially written XLSX. Reopen and validate ZIP/XML and sheet/cell expectations before marking export successful.

## 9. User interface and deployment

Provide these screens: new job (month, template, photos, mode); job progress; review issues; exports/history; connection/settings diagnostics.

Upload returns promptly after durable storage; it never waits for model inference. Support adding photos to an existing batch, pausing/resuming, retrying deferred items, and exporting the current approved snapshot. When files are added to a completed job, reopen it with a new revision and mark the older export as stale. The final browser download is one XLSX; durable JSON/raw response evidence remains available in the app for debugging and re-export.

Docker Compose contains `web` and `worker`, a shared persistent volume, restart policies, and health checks based on process/heartbeat rather than waiting for inference. CPU-only application containers connect to the existing GPU Ollama host; do not deploy a second Ollama server. Document Linux/Windows local development and a CLI using the same services, for example `import-month`, `status`, `resume`, and `export`.

Document connection configuration, optional reverse-proxy upload limits/timeouts, and browser upload failure recovery. Model calls originate from the backend directly to the configured Ollama URL. A proxy timeout can still interrupt backend inference, so recommend a direct LAN endpoint. Do not instruct users to disable every timeout globally.

Make the data volume backup procedure explicit: include originals, database, accepted results, and exports; take a consistent SQLite backup. Logs rotate, and partial thinking/raw responses have configurable storage bounds. Never delete originals or reviewed data automatically to reduce disk usage.

## 10. Implementation milestones and tests

### Milestone 1 — Workbook adapter without a model

Inspect actual fixtures, validate layout, and generate a month from known accepted synthetic records. Test all morning/afternoon boundary times, sums, blank versus zero, leap-year month length, real date formatting, daily ordering, hidden boundary, and 3-D average endpoints. Verify the logo/print layout and all unrelated cells/formulas. Independently check representative MASTER results in Excel or LibreOffice when available. This milestone must pass before inference is connected.

### Milestone 2 — Durable queue and mock Ollama server

Implement ingestion, DB transitions, exclusive worker ownership, checkpoints, and streaming client. A mock server must simulate delayed first chunks and inter-chunk gaps using short configurable test durations, disconnects mid-JSON, 503s, permanent 400s, incomplete generation, malformed schemas, and uncertain cancellation. Test a killed worker mid-task, server outage/recovery, restart during retry delay, duplicate upload, and restart after a response/checkpoint. Previously succeeded tasks must not be called again.

### Milestone 3 — Real vision extraction and calibration

Run the supplied photo against the operator's Ollama endpoint only when reachable/configured. Check date/section/grid mapping and clear/ambiguous cells against manual truth. Gather 10–20 diverse manually checked sheets, including multiple handwriting styles, blank rows, crossed-out numbers, sums, skew, and afternoon pages. Compare thinking modes and request profiles without promising a percentage in advance. Measure exact numeric accuracy, blank/zero confusion, row alignment errors, date assignment accuracy, review workload, and missed errors among autoaccepted cells. Never treat model self-confidence as a calibrated probability.

### Milestone 4 — Review and monthly assembly

Implement independent verification, reconciliation, review edits, multi-page merging, conflict handling, draft/final exports, and issue reports. Test identical and conflicting same-time observations, undated pages, out-of-month dates, missing days, read-only originals, and editing a result while export is in progress. A disagreement must not be silently included in a final workbook.

### Milestone 5 — Month-sized endurance run and handoff

Test 60+ mixed-page images using a mock server and then a real representative batch when available. Close the browser, restart both app processes, interrupt Ollama connectivity, and fail one source deliberately. Confirm all unaffected items complete, the exact interrupted work resumes, and a valid draft/final workbook remains downloadable. Test export/recalculation failure independently of extraction. Record what was tested on actual hardware and what remains untested.

## 11. Acceptance criteria

- A month is uploaded once; the durable worker processes images and passes sequentially.
- No completed extraction is lost after a crash/restart, and successful tasks are not reissued on ordinary resume.
- Long inference does not depend on browser or upload-request timeouts. Outages retain pending work with recoverable status.
- A persistently bad image cannot prevent other images from completing. Every failure/uncertainty appears in a review/report state.
- Blanks remain empty, zeros remain numeric zero, and addition is computed locally from validated terms.
- Only the three requested numerical columns are populated; date/time placement is exact.
- Independent reads and structural checks catch alignment/disagreement cases; accepted cells retain provenance.
- Same-day multiple pages merge correctly without double-counting; conflicting observations require a decision.
- The output preserves the template, MASTER averaging semantics, print layout, logos, and hidden boundary. Sample/out-of-month sheets do not contaminate new-month averages.
- The app automatically generates one monthly XLSX when processing settles, labeled as provisional if needed, and generates the final version after issues are resolved.
- There is no requirement to re-run the model to correct a count, recover an export failure, or download an updated workbook.
- Tests use a mocked Ollama service plus actual workbook fixtures. Real model performance is reported separately and honestly.
- No changes are made to the user's Hermes model or global Ollama configuration.

## 12. Technical references

Verified official documentation; the numeric tuning/timeout values above are proposed app defaults, not vendor guarantees:

- Ollama chat request/streaming/schema/thinking/keep-alive: https://docs.ollama.com/api/chat
- Ollama vision image input: https://docs.ollama.com/capabilities/vision
- Ollama structured outputs: https://docs.ollama.com/capabilities/structured-outputs
- Ollama context, memory residency, concurrency, and keep-alive: https://docs.ollama.com/faq
- Ollama Modelfile parameters: https://docs.ollama.com/modelfile
- HTTPX connect/read/write/pool timeout semantics: https://www.python-httpx.org/advanced/timeouts/
- openpyxl worksheet-copy limitations and workbook loading: https://openpyxl.readthedocs.io/en/stable/tutorial.html

Recheck current APIs during implementation and verify actual installed Ollama/model behavior. The two reference attachments and explicit user rules take precedence over generic OCR assumptions.
