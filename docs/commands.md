# Pool Headcount — Commands

Run commands from the checkout with its virtual environment interpreter. The examples use `python`; substitute `.venv/bin/python` on Linux or `.\.venv\Scripts\python.exe` on Windows. For a running container deployment, prefix commands with `docker compose exec web`, for example `docker compose exec web python -m app.cli status JOB_ID`.

`JOB_ID`, `EXPORT_ID`, and filesystem paths below are placeholders. Status JSON exposes source, task, issue, attempt, cell, and export identifiers. Settings come from the same environment and `DATA_DIR` as the services. The CLI shares application services directly; it does not call the HTTP API.

## Complete CLI reference

| Command after `python -m app.cli` | Effect |
| --- | --- |
| `migrate` | Initialize/upgrade SQLite and queue legacy export migration where needed. |
| `worker-health` | Exit 0 for a recent worker heartbeat, 1 otherwise; does not run migrations first. |
| `diagnostics` | Check Ollama version, model capabilities, and available digest. |
| `import-month --month YYYY-MM --template PATH --photos PATH [--mode MODE]` | Create a batch. `MODE` is `new-month` (default) or `continuation`; photos can be a folder, ZIP, or file. |
| `status JOB_ID` | Print batch state and detailed evidence as JSON. |
| `pause JOB_ID` | Stop new dispatch after the active call; preserve work. |
| `resume JOB_ID` | Queue a paused/cancelled batch and clear its diagnostic. |
| `cancel JOB_ID` | Mark cancelled; retain data and allow later resume. |
| `retry JOB_ID` | Reset failed tasks and deferred sources for another attempt. |
| `coverage JOB_ID` | Audit acknowledgement that missing days/sections have no source or are not applicable. |
| `refresh JOB_ID` | Reconcile saved readings using current settings; refuse while OCR is in flight. |
| `export JOB_ID` | Generate or return the export for the current revision without model inference. |
| `add JOB_ID PATH` | Add photos from folder, ZIP, or file; deduplicate identical uploads. |
| `backup DESTINATION` | Snapshot database and referenced artifacts to a new directory outside `DATA_DIR`. |
| `recalculate EXPORT_ID` | Run configured LibreOffice on an export and retain a separately verified artifact. |

`python -m app.cli --help` and `python -m app.cli import-month --help` show argument syntax. Except for `worker-health`, commands run migrations before their action. Most results print JSON; failures propagate as command errors. Do not use a live data directory merely to explore mutating commands.

## Import and follow a batch

```sh
python -m app.cli import-month --month 2026-10 --template "Head Counts.xlsx" --photos /path/to/photos --mode new-month
python -m app.cli status JOB_ID
python -m app.cli add JOB_ID /path/to/more-photos.zip
```

The import command returns `{"job": "..."}`. A separately running worker is required for OCR. CLI import/add use automatic photo layout; there is no CLI layout flag. Use the web form or source configuration API for explicit `new-paper`/`monthly` layouts.

## Manage work and regenerate

```sh
python -m app.cli pause JOB_ID
# Wait until status shows no in_flight tasks.
python -m app.cli refresh JOB_ID
python -m app.cli resume JOB_ID
python -m app.cli export JOB_ID
```

`refresh` retains reviews and successful readings. `retry` targets failed tasks rather than repeating completed calls. Acknowledging coverage does not fabricate counts. Reprocessing a photo or correcting a cell requires the [API](./api.md) or browser review controls.

## Backup and recalculation

```sh
python -m app.cli backup /path/outside/data/backup-2026-10-15
python -m app.cli recalculate EXPORT_ID
```

The backup destination must not already exist. Pause all batches and wait for active inference first. In containers, mount a backup directory; see the full [deployment procedure](./deployment.md). Recalculation requires an installed executable configured by `LIBREOFFICE`; it is not bundled in the application image.

## Other entry points

- `python -m app.worker` runs the single durable worker.
- `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` runs the web service.
- `python -m app.calibration --output calibration-output` runs a live, small manual-truth benchmark. It requires a compatible verification profile and an isolated data directory; see [testing](./testing.md).
- `python scripts/prepare_release.py v0.1.0 ghcr.io/willtheorangeguy/ucac-ocr /tmp/release-files` generates deployment assets, without publishing anything. Use a fresh output directory outside the checkout.
