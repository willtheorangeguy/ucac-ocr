# Pool Headcount — Architecture

The application separates upload/review HTTP requests from long model calls. FastAPI persists inputs and returns a job URL; a separately running worker reads durable task records, calls Ollama sequentially, reconciles readings, and exports immutable workbooks. Closing the browser does not affect processing.

```text
Browser or CLI
      |
      v
Ingestion -----> originals + normalized images
      |
      v
SQLite jobs/sources -> preprocessing -> pages + crop tasks
      |                                      |
      |                                  single worker
      |                                      |
      |                             streamed Ollama requests
      |                                      |
      +<----- readings + attempts + raw responses
      |
 reconciliation <---- audited review decisions
      |
 cells + issues -> workbook export -> revisioned XLSX + IMPORT REPORT
```

## Components and project layout

| Path | Responsibility |
| --- | --- |
| [app/main.py](../app/main.py), `templates/`, `static/` | HTTP routes, server-rendered views, table selection, and polling UI. |
| [app/cli.py](../app/cli.py), [services.py](../app/services.py) | CLI operations, status, controls, source configuration, and cell corrections. |
| [ingestion.py](../app/ingestion.py), [storage.py](../app/storage.py) | ZIP validation, decoding, deduplication, content hashes, and atomic artifact writes. |
| [preprocessing.py](../app/preprocessing.py) | Perspective detection, grid fitting, sections, rectification, and alternate crops. |
| [worker.py](../app/worker.py) | Ownership, heartbeat, queue dispatch, retries, recovery, and settled exports. |
| [ollama_client.py](../app/ollama_client.py), [prompts.py](../app/prompts.py), [schemas.py](../app/schemas.py) | Model capability checks, bounded streaming, extraction prompts, and structural validation. |
| [count_text.py](../app/count_text.py), [reconciliation.py](../app/reconciliation.py) | Numeric normalization, copy-down, A/B and cross-source agreement, and reviews. |
| [layout.py](../app/layout.py), [workbook.py](../app/workbook.py), [monthly_workbook.py](../app/monthly_workbook.py) | Time/cell mapping, OOXML validation, and monthly workbook generation. |
| [exporting.py](../app/exporting.py) | Export snapshots, per-job file locks, revision checks, checksums, and optional recalculation. |
| [db.py](../app/db.py), [migrations/001.sql](../app/migrations/001.sql) | SQLite connections, transactions, and startup upgrades. |
| [assets/README.md](../app/assets/README.md) | Provenance of the sanitized monthly fallback template. |
| [tests/](../tests), [validation/](../validation) | Mock regression tests and historical validation evidence/scripts. |
| [scripts/prepare_release.py](../scripts/prepare_release.py) | Generate version-pinned release deployment files. |

## Storage and schema

`DATA_DIR/jobs.sqlite3` uses WAL, foreign keys, a 30-second busy timeout, and immediate write transactions. Schema version 1 is established by SQL; `migrate()` also handles additive compatibility changes and one-time legacy export regeneration. Web startup and the worker call migrations, so they must use the same data directory.

| Table | Purpose |
| --- | --- |
| `schema_version` | Base schema marker. |
| `jobs` | Month, mode, immutable template path/hash, state, revisions, diagnostic, and coverage acknowledgement. |
| `sources` | Original/normalized photo paths, hash, filename, assigned/observed dates, layout hint, geometry, and version. Unique photo hash per job. |
| `pages` | Versioned rectified sections, transforms, and image paths. |
| `tasks` | Unique task key, version, pass, crop, expected times, state, retry counters, and schedule. |
| `attempts` | Start/finish status, raw response path, profile/model metadata, error, and metrics. |
| `readings` | Validated per-task cell readings. |
| `cells` | Reconciled date/time/column values, kind, acceptance, provenance, and reviewed flag. |
| `issues` | Unique job issue key, details, source/cell association, and resolution status. |
| `decisions` | Audited review/control actions with reviewer, note, and time. |
| `exports` | Immutable revision path, checksum, draft flag, report, and recalculation metadata. |
| `worker_owner` | Single generation, heartbeat, active task, and cooldown record. |

Per-job subdirectories hold templates, originals, normalized images, rectified pages, crops, response streams, and exports. `worker.lock` and `worker.log` live at the data root; export locks are per job. Paths are stored in database records, so restoring to another absolute path requires explicit metadata migration. Artifacts are not automatically purged.

## State and recovery

Jobs move from `ingesting` to `queued`/`running` and eventually `completed` or `completed_with_issues`. `waiting_for_ollama` preserves outage diagnostics; permanent configuration errors pause the job. Export failures use `awaiting_review`. Manual `paused` and `cancelled` states stop dispatch after an active call and retain evidence. Reviews and added sources advance the revision and reopen eligible batches.

Tasks progress through `pending`, `in_flight`, and `succeeded`, or `retry_wait`/`failed`. Split retries supersede a parent and create smaller bands; disabled B tasks can be `skipped`. Sources can be `pending`, `processing`, `succeeded`, `needs_review`, `deferred`, or `failed` (invalid input). A deferred bad photo does not block later eligible work.

An OS file lock and database generation allow one worker to own a data directory. Startup marks abandoned attempts interrupted and retries unfinished tasks after cooldown. Completed readings and task responses are committed together; transactions never span inference requests. Streaming resumes by retrying the unfinished task, not by resuming a partial remote response.

Availability failures do not spend content-retry budgets. After five consecutive availability failures, short health probes gate retries. Content failures receive bounded retries and smaller bands/larger output budgets; resource failures get a smaller-context attempt before deferral. Permanent HTTP/model errors pause for operator action. A remote request may continue after local disconnect, so cooldown is part of recovery.

Exports snapshot a revision outside long-held database transactions and use an export lock. If a review advances the job while export runs, the old artifact remains tied to its original revision; a newer export can follow. See [deployment](./deployment.md) for backup/restore and [rules](./rules.md) for workbook semantics.
