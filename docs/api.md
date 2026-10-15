# Pool Headcount — API

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

## Import example

```sh
curl -F month=2026-10 -F mode=new-month \
  -F 'template=@Head Counts.xlsx' -F 'photos=@morning.jpg' \
  -F photo_layout=legacy http://localhost:8000/jobs
```

Read the `Location` header in the 303 response for the new batch URL/ID. The worker is independent of this HTTP request.

## Date and table configuration

POST this shape to `/api/jobs/JOB_ID/sources/SOURCE_ID`:

```json
{
  "date": "2026-10-09",
  "confirm": false,
  "reviewer": "operator",
  "geometry": [
    {"section": "morning", "layout": "legacy", "corners": [[10,10],[900,10],[900,600],[10,600]]},
    {"section": "afternoon", "layout": "legacy", "corners": [[10,700],[900,700],[900,1400],[10,1400]]}
  ]
}
```

Coordinates are illustrative: use pixel positions in the stored normalized image, clockwise from top-left. Geometry contains one or two tables. Sections are `auto`, `morning`, `afternoon`, or `both`; `auto` detects row count. Two tables must have different sections and cannot include `both`. Layout values match `photo_layout` above. Date must fall within the batch month. A date-only assignment can reuse readings; `confirm:true` explicitly audits overriding recognized contradictory dates. Pause and wait for active OCR before changing a source. Geometry changes create a new version and regenerate work.

## Review and direct correction

For `/api/jobs/JOB_ID/review/ISSUE_ID`:

```json
{"action":"value","value":32,"note":"Checked against photo","reviewer":"operator"}
```

Use `action:"blank"` for an empty cell, or `action:"acknowledge"` for source issues and reviewed-new-evidence acknowledgement. A cell issue normally requires a numeric or blank decision. Numeric values must be integers from 0 through 1,000,000,000; reviewer must be nonempty.

For `/api/jobs/JOB_ID/cells`, add the stored cell key:

```json
{"key":"2026-10-09|05:15|group","action":"value","value":32,"note":"Correction","reviewer":"operator"}
```

`group` is the compatibility key for Internal. Corrections create audit decisions and advance the job revision. They do not call the model.

## Errors and integration limits

Application `ValueError`s become HTTP 400 with `{"error":"message"}`. FastAPI field validation can return 422; explicit missing file records return 404. Cross-origin browser writes return 403. These conventions do not guarantee every malformed JSON body has a structured 400 response; callers should send the documented types and inspect non-success status codes.

## Ollama API consumed

The [client](../app/ollama_client.py) uses `GET /api/version`, `POST /api/show` with the model, and `GET /api/tags` for preflight metadata; short health probes use `/api/version`. Extraction uses streamed `POST /api/chat` with the configured model, schema, options, boolean `think`, `keep_alive`, and a base64 image in a fresh user message. No conversation history or tool definitions are sent.

The client disables environment proxy discovery (`trust_env=False`), records raw stream chunks and timing, and accepts complete validated JSON only after a terminal `done_reason=stop`. Invalid, truncated, or oversized responses fail and enter the worker's retry/review flow. See [architecture](./architecture.md) and [configuration](./configuration.md).
