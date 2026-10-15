# Installation

<!-- markdownlint-disable MD046 -->

## Requirements

Use Docker with Compose for the published bundle or a source build. Docker Desktop must use Linux containers. The repository specifies no minimum Docker version. Direct source installs use Python 3.14, the interpreter used for the pinned dependency set. Ollama must be version 0.17.1 or later with a vision-capable model installed. `THINK=true` additionally requires thinking capability.

Check the tools for your selected method:

```bash
docker --version
docker compose version
python --version
git --version
```

Supported inputs are a legacy daily-sheet workbook or Fall 2026 monthly workbook containing `BLANK`, and JPEG/MPO, PNG, or WebP photos. ZIP uploads can contain multiple photos. MOV companions are skipped; HEIC is unsupported. Keep SQLite on local disk. The CPU application services do not install or host Ollama.

## Install methods

=== "Published bundle"

    Download and extract `ucac-ocr-v0.1.0.zip` from the [release](https://github.com/willtheorangeguy/ucac-ocr/releases/tag/v0.1.0). On Windows, use Explorer or `Expand-Archive`. If you download individual assets, save `default.env` as `.env` alongside `compose.yaml`.

    With GitHub CLI and unzip installed:

    ```bash
    gh release download v0.1.0 --repo willtheorangeguy/ucac-ocr --pattern ucac-ocr-v0.1.0.zip
    unzip ucac-ocr-v0.1.0.zip
    ```

    Set `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in `.env`. Start services from the extracted directory:

    ```bash
    docker compose up -d
    docker compose logs -f worker
    ```

    Database migrations run automatically. Both services share `pool-data` at `/data`. This method does not require source files.

=== "Docker source build"

    Build the checked-out source instead of a published release:

    ```bash
    git clone https://github.com/willtheorangeguy/ucac-ocr.git
    cd ucac-ocr
    cp .env.example .env
    ```

    In PowerShell, use `Copy-Item .env.example .env`. Edit the copied file for your server/model, then run:

    ```bash
    docker compose -f compose.yaml -f compose.build.yaml up -d --build
    ```

    Use both Compose files consistently for later lifecycle commands. The override gives both services the `pool-headcount:local` image.

=== "Windows source"

    From a full checkout, with Python 3.14 selected:

    ```powershell
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.lock
    Copy-Item .env.example .env
    ```

    Edit `.env` for your Ollama server/model. Start the web process:

    ```powershell
    .\.venv\Scripts\python.exe -m app.cli migrate
    .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    ```

    In a second terminal, from the same checkout:

    ```powershell
    .\.venv\Scripts\python.exe -m app.worker
    ```

    After setup, the helper starts both processes in hidden windows:

    ```powershell
    powershell -ExecutionPolicy Bypass -File .\start.ps1
    ```

    It requires port 8000 to be free and records process IDs in `.local-processes.json`. Pause batches with the [CLI](commands.md), wait for active inference to checkpoint, then run:

    ```powershell
    powershell -ExecutionPolicy Bypass -File .\stop.ps1
    ```

    The stop helper force-terminates its recorded processes. It does not pause jobs itself.

=== "Linux source"

    ```bash
    git clone https://github.com/willtheorangeguy/ucac-ocr.git
    cd ucac-ocr
    python3.14 -m venv .venv
    .venv/bin/python -m pip install -r requirements.lock
    cp .env.example .env
    ```

    Edit `.env` for your Ollama server/model. Start web:

    ```bash
    .venv/bin/python -m app.cli migrate
    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    ```

    In a second terminal, from the same checkout:

    ```bash
    .venv/bin/python -m app.worker
    ```

    Both processes must use the same working directory and `DATA_DIR`.

## Verify the installation

For Compose:

```bash
docker compose ps
docker compose exec web python -m app.cli diagnostics
curl --fail http://localhost:8000/health
```

Expect two healthy services, diagnostics naming the configured vision model, and the health body:

```json
{"web":"ok"}
```

For source deployments, run `python -m app.cli diagnostics` and `python -m app.cli worker-health` using the installed interpreter. The latter exits 0 for a recent worker heartbeat. Web health does not establish worker or Ollama readiness. Open the [local app](http://localhost:8000) and follow [Getting started](getting-started.md).

## Upgrading

Back up first. Change `POOL_HEADCOUNT_IMAGE` in `.env` for a published deployment, then run:

```bash
docker compose pull
docker compose up -d
```

For source builds, update the checkout and rebuild with both Compose files. Read [Deployment and recovery](deployment.md) for migrations, pauses, rollback, and persistent storage.

## Uninstalling

Pause batches and wait for active tasks before stopping services. For Compose, remove services while retaining the data volume:

```bash
docker compose down
```

For source installs, stop web and worker, then remove the virtual environment and checkout only after keeping a backup of `DATA_DIR`. Original evidence and exports need separate retention decisions.

!!! danger "Retain the data volume"
    `docker compose down -v` deletes the persistent volume. Run it only when you intend to destroy its database, originals, reviews, and exports.
