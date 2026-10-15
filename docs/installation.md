# Pool Headcount — Installation

## Prerequisites

- An existing HTTP(S) Ollama endpoint, version 0.17.1 or later as required by the application's preflight check, with a vision-capable model already installed. The default model name is `qwen3.5-hermes:64k`; thinking capability is required only when `THINK=true`.
- A supported legacy daily-sheet workbook or Fall 2026 monthly workbook with `BLANK`, plus JPEG/MPO, PNG, or WebP photos. ZIP uploads can contain multiple photos; MOV companions are skipped. HEIC is not supported.
- Local disk for the database and artifacts. Do not put SQLite on SMB/NFS.
- For containers: Docker Engine or Docker Desktop using Linux containers, with Compose available as `docker compose`.
- For source installs: Git and Python 3.14. The pinned dependencies were prepared with Python 3.14; other interpreter versions are not the documented baseline.

The application services run on CPU. Ollama owns inference hardware and model setup separately. No Ollama service is included in Compose.

## Published deployment bundle

Download and extract `ucac-ocr-v0.1.0.zip` from the [release](https://github.com/willtheorangeguy/ucac-ocr/releases/tag/v0.1.0). With GitHub CLI and unzip installed, the equivalent is:

```sh
gh release download v0.1.0 --repo willtheorangeguy/ucac-ocr --pattern ucac-ocr-v0.1.0.zip
unzip ucac-ocr-v0.1.0.zip
```

On Windows, use Explorer or `Expand-Archive`. If downloading assets individually, download `compose.yaml` and `default.env`, then save `default.env` as `.env`. Run Compose from that directory.

Set `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in `.env`, then:

```sh
docker compose up -d
docker compose logs -f worker
```

Open <http://localhost:8000>. Migrations run automatically at service startup. Web and worker share the named `pool-data` volume. Published containers require no source checkout. For registry authentication errors, see [troubleshooting](./troubleshooting.md).

## Build from source with Docker

This uses the checked-out source rather than the release image:

```sh
git clone https://github.com/willtheorangeguy/ucac-ocr.git
cd ucac-ocr
cp .env.example .env
# Edit .env for your Ollama server and model.
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

In PowerShell, replace `cp` with `Copy-Item .env.example .env`. Use both Compose files for later build, log, and lifecycle commands for this deployment. The override gives both services the local `pool-headcount:local` image.

## Windows source installation

From a full checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
# Edit .env for your Ollama server and model.
.\.venv\Scripts\python.exe -m app.cli migrate
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the worker in a second terminal in the same project directory:

```powershell
.\.venv\Scripts\python.exe -m app.worker
```

After setup, the provided Windows helper starts both processes in hidden windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

It requires port 8000 to be free and records process IDs in `.local-processes.json`. Pause batches through the [CLI or API](./commands.md) and wait for the active request to checkpoint before running `powershell -ExecutionPolicy Bypass -File .\stop.ps1`. The stop helper force-terminates its recorded processes; it does not pause jobs itself.

## Linux source installation

```sh
git clone https://github.com/willtheorangeguy/ucac-ocr.git
cd ucac-ocr
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
cp .env.example .env
# Edit .env for your Ollama server and model.
.venv/bin/python -m app.cli migrate
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, from the same checkout:

```sh
.venv/bin/python -m app.worker
```

Keep the working directory and `DATA_DIR` consistent between both processes. Open <http://localhost:8000>. The web process does not execute OCR by itself.

## Verify setup

Run `python -m app.cli diagnostics` with the installed interpreter, or `docker compose exec web python -m app.cli diagnostics`. Check `/health` and `python -m app.cli worker-health` separately: web health does not establish worker or model readiness.

Continue with [configuration](./configuration.md), [quickstart](./quickstart.md), and [deployment](./deployment.md).
