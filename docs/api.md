# API

FastAPI exposes interactive OpenAPI at `/docs`, ReDoc at `/redoc`, and the schema at `/openapi.json`. The API has no authentication. Keep the service on localhost or behind an access-controlled reverse proxy. Browser writes carrying an `Origin` whose netloc differs from the `Host` header receive HTTP 403. Requests without `Origin` are accepted; this check is not authentication.

## Route reference

| Method | Path | Purpose/input |
| --- | --- | --- |
| GET | `/` | Batch list and multipart import form. |
| GET | `/jobs/{job}` | Batch report UI. |
| GET | `/settings` | Settings display. |
| GET | `/health` | Query the schema table; return `{"web":"ok"}`. Does not check Ollama or worker. |
| GET | `/api/settings/diagnostics` | Ollama preflight; `ok:true` plus metadata, or `ok:false` plus diagnostic. |
| POST | `/jobs` | Multipart: `month` (`YYYY-MM`), `mode`, workbook `template`, repeated `photos`, optional `photo_layout` (default `auto`). Returns 303 redirect to batch page. |
| GET | `/api/jobs/{job}` | Batch, sources, tasks, open issues, exports, worker, attempts, cells, and ETA as JSON. |
| POST | `/api/jobs/{job}/photos` | Multipart repeated `photos` and optional `photo_layout`; returns `{"added":N}`. |
| POST | `/api/jobs/{job}/control/{action}` | `pause`, `resume`, `cancel`, `retry`, `coverage`, or `refresh`; returns `{"ok":true}`. |
| POST | `/api/jobs/{job}/export` | Generate/return current export record, including ID, path, checksum, revision, draft flag, and report. |
| POST | `/api/jobs/{job}/sources/{sid}` | Assign date and/or geometry; JSON described below. |
| POST | `/api/jobs/{job}/sources/{sid}/detect` | Detect a box from the normalized image, retaining saved layout choices; returns geometry. |
| POST | `/api/jobs/{job}/sources/{sid}/reprocess` | Create a new source version for explicit reprocessing. |
| POST | `/api/jobs/{job}/review/{issue_id}` | Submit JSON review action. |
| POST | `/api/jobs/{job}/cells` | Submit JSON correction to an existing cell with provenance. |
| GET | `/files/source/{sid}` | Normalized PNG; `?original=true` downloads the original file. |
| GET | `/files/crop/{task_id}` | Stored crop PNG. |
| GET | `/files/attempt/{attempt_id}` | Stored NDJSON attempt stream. |
| GET | `/files/export/{export_id}` | XLSX download named `YYYY-MM-headcounts.xlsx`; `?recalculated=true` selects optional recalculated artifact. |
| POST | `/api/exports/{export_id}/recalculate` | Run LibreOffice; return separate artifact path. |

`photo_layout` accepts `auto`, `legacy`, `new-paper`, or `monthly`. Status returns database-oriented records; some columns such as `geometry`, `result`, `report`, and `provenance` are serialized JSON strings inside those records. ETA is null until there are at least three successful attempts. JSON bodies read directly from `Request` are described here because generated OpenAPI does not declare their fields.

## Example setup

Use the checked-in photo/workbook in a disposable source deployment. These examples create and mutate a batch. Start web on port 8000, keep its worker stopped until the source configuration example is complete, and run commands from the source checkout. Curl prints the actual response bodies; identifiers are read from the returned records.

```bash
base=http://localhost:8000
job_url=$(curl --fail --silent --show-error --output /dev/null \
  --write-out '%{redirect_url}' \
  -F month=2026-10 -F mode=new-month \
  -F 'template=@tests/fixtures/Head Counts.xlsx' \
  -F 'photos=@tests/fixtures/morning-2026-10-09.jpg' \
  -F photo_layout=legacy "$base/jobs")
job_id=${job_url##*/}
source_id=$(curl --fail --silent "$base/api/jobs/$job_id" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["sources"][0]["id"])')
```

The import response is HTTP 303 with a `Location` header naming `/jobs/{job}`. It has no JSON response body. Form fields are `month` and `mode` strings, one workbook file, repeated photo files, and optional layout. Missing required fields return 422; invalid supported values raise application errors. The worker is independent of this request.

## Read-only routes

These calls use `base` and `job_id` from the setup:

```bash
curl --fail --include "$base/"
curl --fail --include "$base/jobs/$job_id"
curl --fail --include "$base/settings"
curl --fail --include "$base/health"
curl --fail --include "$base/api/settings/diagnostics"
curl --fail --include "$base/api/jobs/$job_id"
```

| Call | Successful response | Error behavior |
| --- | --- | --- |
| `GET /` | 200 HTML: batch list and multipart upload form. | Storage/template failures can return 500. |
| `GET /jobs/{job}` | 200 HTML: four-step batch report. | Unknown job returns 400. |
| `GET /settings` | 200 HTML: settings and diagnostics display. | Template failures can return 500. |
| `GET /health` | 200 JSON: `{"web":"ok"}`. | Database query failure returns 500. |
| `GET /api/settings/diagnostics` | 200 JSON with `ok:true`, version, model, capabilities, and optional digest. | Preflight errors still return 200, with `ok:false` and `diagnostic`. |
| `GET /api/jobs/{job}` | 200 JSON: the job record plus `sources`, `tasks`, `issues`, `exports`, `worker`, `attempts`, `cells`, and `eta_seconds`. | Unknown job returns 400 with `{"error":"Unknown job"}`. |

Path job/source identifiers are strings. Issue, task, attempt, and export identifiers are integers. The state fields and nested records are described in [Architecture](architecture.md).

## Batch mutations

```bash
curl --fail --include -X POST "$base/api/jobs/$job_id/control/pause"
curl --fail --include -X POST "$base/api/jobs/$job_id/photos" \
  -F 'photos=@tests/fixtures/morning-2026-10-09.jpg' -F photo_layout=legacy
curl --fail --include -X POST "$base/api/jobs/$job_id/export"
```

The control response is 200 JSON `{"ok":true}`. `action` accepts `pause`, `resume`, `cancel`, `retry`, `coverage`, and `refresh`; no request body is required. Unknown jobs/actions return 400. Refresh also returns 400 while inference is in flight.

Photo addition returns 200 JSON `{"added":0}` for this duplicate fixture, or a positive count for new hashes. The form accepts repeated `photos` files and optional `photo_layout`. Invalid layouts, unknown/cancelled jobs, and exceeded limits return 400. Missing required files can return 422.

Export returns a 200 JSON database export record, including integer `id`, `job_id`, `revision`, `path`, `checksum`, integer `draft`, `created`, serialized `report`, and `recalculated`. It can produce a draft before OCR. Template checksum changes raise 400; filesystem failures or an unknown export job can return 500. Status includes generated export IDs for later downloads.

## Date and table configuration

The bundled normalized 1080 × 1440 fixture has this verified morning geometry. Save it before starting its worker, or pause and wait for active inference to finish:

```bash
curl --fail --include -X POST "$base/api/jobs/$job_id/sources/$source_id" \
  -H 'Content-Type: application/json' \
  --data '{"date":"2026-10-09","confirm":false,"reviewer":"operator","geometry":[{"section":"morning","layout":"legacy","corners":[[154,262],[918,252],[968,1185],[138,1200]]}]}'
```

Success returns 200 JSON `{"ok":true}`. Unknown source, out-of-month date, invalid geometry/layout, or active inference returns 400. The fixture coordinates apply only to that normalized photo.

```bash
curl --fail --include -X POST "$base/api/jobs/$job_id/sources/$source_id/detect"
curl --fail --include -X POST "$base/api/jobs/$job_id/sources/$source_id/reprocess"
```

Detection returns 200 JSON `{"geometry":[...]}`, containing detected section/corner/layout dictionaries. A missing readable image, invalid grid, concurrent version change, or active inference raises 400. Reprocess returns 200 JSON `{"ok":true}` and returns 400 for unknown sources or active inference. Neither route requires a body.

For other photos, use pixel positions in their stored normalized image, clockwise from top-left. Geometry contains one or two tables. Sections are `auto`, `morning`, `afternoon`, or `both`; `auto` detects row count. Two tables must have different sections and cannot include `both`. Layout values match `photo_layout` above. Date must fall within the batch month. A date-only assignment can reuse readings; `confirm:true` explicitly audits overriding recognized contradictory dates. Pause and wait for active OCR before changing a source. Geometry changes create a new version and regenerate work.

## Review and direct correction

Start/resume the worker and wait until status contains cells and any unresolved issues. Pause and wait for active work before experimenting further. Derive identifiers from the batch rather than copying IDs from another deployment:

```bash
issue_id=$(curl --fail --silent "$base/api/jobs/$job_id" \
  | python -c 'import json,sys; rows=json.load(sys.stdin)["issues"]; print(rows[0]["id"] if rows else "")')
if [ -n "$issue_id" ]; then
  curl --include -X POST "$base/api/jobs/$job_id/review/$issue_id" \
    -H 'Content-Type: application/json' \
    --data '{"action":"value","value":32,"note":"Checked against photo","reviewer":"operator"}'
fi
```

Success returns 200 JSON `{"ok":true}`. The example applies only when that issue concerns a cell that reads 32. Source-level issues require `action:"acknowledge"`; other cells can use `action:"blank"`. Invalid actions, wrong decision type for an issue, unknown issues, empty reviewer, or values outside 0–1,000,000,000 return 400. Acknowledgement is also allowed for reviewed-new-evidence issues.

The checked first-row Internal value in the bundled photo is 32. After its cells exist, a direct correction is:

```bash
curl --fail --include -X POST "$base/api/jobs/$job_id/cells" \
  -H 'Content-Type: application/json' \
  --data '{"key":"2026-10-09|05:15|group","action":"value","value":32,"note":"Correction","reviewer":"operator"}'
```

Success returns 200 JSON `{"ok":true}`. Unknown cells or invalid decision fields return 400. `group` is the compatibility key for Internal. Corrections create audit decisions and advance the revision without calling the model.

## Evidence and export downloads

After processing and exporting, read the recorded identifiers:

```bash
status_file=$(mktemp /tmp/ucac-api-status.XXXXXX)
curl --fail --silent "$base/api/jobs/$job_id" > "$status_file"
task_id=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["tasks"][0]["id"])' "$status_file")
attempt_id=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["attempts"][0]["id"])' "$status_file")
export_id=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["exports"][0]["id"])' "$status_file")
curl --fail "$base/files/source/$source_id" --output /tmp/ucac-source.png
curl --fail "$base/files/source/$source_id?original=true" --output /tmp/ucac-original.jpg
curl --fail "$base/files/crop/$task_id" --output /tmp/ucac-crop.png
curl --fail "$base/files/attempt/$attempt_id" --output /tmp/ucac-attempt.ndjson
curl --fail "$base/files/export/$export_id" --output /tmp/ucac-headcounts.xlsx
```

| Route | Successful response body | Errors |
| --- | --- | --- |
| `/files/source/{sid}` | 200 normalized PNG bytes, or original file bytes with `original=true`. | Missing source/normalized path: 404. Missing artifact on disk can return 500. |
| `/files/crop/{task_id}` | 200 PNG bytes. | Unknown task: 404. Missing disk file can return 500. |
| `/files/attempt/{attempt_id}` | 200 NDJSON stream, downloaded as `attempt-N.ndjson`. | Unknown attempt or missing disk file: 404. |
| `/files/export/{export_id}` | 200 XLSX bytes; download filename `YYYY-MM-headcounts.xlsx`. | Unknown export or absent recalculated path: 404. Missing disk file can return 500. |

Optional recalculation requires `LIBREOFFICE` configured in the server environment:

```bash
curl --fail --include -X POST "$base/api/exports/$export_id/recalculate"
curl --fail "$base/files/export/$export_id?recalculated=true" --output /tmp/ucac-recalculated.xlsx
```

Recalculation success returns 200 JSON `{"path":"..."}` naming the separate verified artifact. Missing executable configuration, unknown export, or failed workbook verification raises 400. Executable/conversion failures can return 500. The original remains retained. The download query is boolean and defaults to false.

## Errors and integration limits

Application `ValueError`s become HTTP 400 with `{"error":"message"}`. FastAPI field validation can return 422; explicit missing file records return 404. Cross-origin browser writes return 403. These conventions do not guarantee every malformed JSON body has a structured 400 response; callers should send the documented types and inspect non-success status codes.

## Ollama API consumed

The [client](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/app/ollama_client.py) uses `GET /api/version`, `POST /api/show` with the model, and `GET /api/tags` for preflight metadata; short health probes use `/api/version`. Extraction uses streamed `POST /api/chat` with the configured model, schema, options, boolean `think`, `keep_alive`, and a base64 image in a fresh user message. No conversation history or tool definitions are sent.

The client disables environment proxy discovery (`trust_env=False`), records raw stream chunks and timing, and accepts complete validated JSON only after a terminal `done_reason=stop`. Invalid, truncated, or oversized responses fail and enter the worker's retry/review flow. See [architecture](./architecture.md) and [configuration](./configuration.md).
