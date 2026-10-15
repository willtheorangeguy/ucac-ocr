# Commands

Run commands from the checkout with its virtual environment interpreter. The examples use `python`; substitute `.venv/bin/python` on Linux or `.\.venv\Scripts\python.exe` on Windows. For a running container deployment, prefix commands with `docker compose exec web`, for example `docker compose exec web python -m app.cli status JOB_ID`.

`JOB_ID`, `EXPORT_ID`, and filesystem paths below are placeholders. Status JSON exposes source, task, issue, attempt, cell, and export identifiers. Settings come from the same environment and `DATA_DIR` as the services. The CLI shares application services directly; it does not call the HTTP API.

## Command reference

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

## Arguments and flags

`import-month` is the only subcommand with options. Other job commands accept a positional job ID; `add` adds a photo path, `backup` accepts a new destination, and `recalculate` accepts an integer export ID.

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--month` | `YYYY-MM` string | required | Target calendar month, such as `2026-10`. |
| `--template` | file path | required | Supported workbook path. |
| `--photos` | file/directory path | required | Photo, ZIP, or recursively read folder. |
| `--mode` | string enum | `new-month` | `new-month` or `continuation`. |

## Worked command sequence

This POSIX shell example uses the checked-in workbook/photo and a temporary data directory, with no worker running against it. Run from an installed source checkout. It exercises durable commands without sending OCR requests or changing operator data. `job_id` and `export_id` come from real command responses rather than hardcoded IDs.

```bash
export DATA_DIR="$(mktemp -d /tmp/ucac-cli-example.XXXXXX)"
python -m app.cli migrate
job_id=$(python -m app.cli import-month --month 2026-10 \
  --template 'tests/fixtures/Head Counts.xlsx' \
  --photos tests/fixtures/morning-2026-10-09.jpg --mode new-month \
  | python -c 'import json,sys; print(json.load(sys.stdin)["job"])')
python -m app.cli status "$job_id"
python -m app.cli pause "$job_id"
python -m app.cli refresh "$job_id"
python -m app.cli resume "$job_id"
python -m app.cli cancel "$job_id"
python -m app.cli resume "$job_id"
python -m app.cli retry "$job_id"
python -m app.cli add "$job_id" tests/fixtures/morning-2026-10-09.jpg
python -m app.cli coverage "$job_id"
export_id=$(python -m app.cli export "$job_id" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
python -m app.cli pause "$job_id"
backup_parent=$(mktemp -d /tmp/ucac-cli-backup.XXXXXX)
python -m app.cli backup "$backup_parent/snapshot"
```

The import prints a job identifier. Adding the same photo returns zero new sources because hashes are deduplicated. With no worker, the export is a draft with pending evidence. Coverage acknowledgement creates no counts. `refresh` retains successful readings/reviews and refuses an in-flight task. `retry` resets failed tasks rather than reissuing completed ones.

CLI import/add use automatic photo layout. There is no CLI layout flag. Use the browser or [API](api.md) for explicit revised-paper/monthly layouts and source/cell corrections.

## Diagnostics and worker health

Run diagnostics in the configured deployment environment:

```bash
python -m app.cli diagnostics
python -m app.cli worker-health
```

Diagnostics contacts the configured Ollama endpoint. It prints version, model, capabilities, and digest metadata on success. Worker health exits 0 only with a recent heartbeat. It exits 1 in the isolated example above because no worker has acquired the data directory.

## Optional recalculation

After installing LibreOffice, the previous command sequence supplies a real `export_id`. With that executable configured, run:

```bash
LIBREOFFICE=/usr/bin/libreoffice python -m app.cli recalculate "$export_id"
```

The command requires the executable to exist and can fail if conversion or verification fails. It preserves the original artifact and exposes a verified separate result on success. The application image does not bundle LibreOffice. See [Deployment and recovery](deployment.md) for mounted backup directories and restore constraints.

## Other entry points

- `python -m app.worker` runs the single durable worker.
- `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` runs the web service.
- `python -m app.calibration --output calibration-output` runs a live, small manual-truth benchmark. It requires a compatible verification profile and an isolated data directory; see [testing](./testing.md).
- `python scripts/prepare_release.py v0.1.0 ghcr.io/willtheorangeguy/ucac-ocr /tmp/release-files` generates deployment assets, without publishing anything. Use a fresh output directory outside the checkout.
