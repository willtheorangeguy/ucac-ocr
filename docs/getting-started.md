# Getting started

Use the published container bundle to produce a first workbook. This path does not require a source checkout or install an Ollama model.

## Prerequisites

- Docker Engine or Docker Desktop using Linux containers, with the Compose plugin. The repository does not specify a minimum Docker/Compose version. Check your installed versions with the commands below.
- An existing Ollama server, version 0.17.1 or later, with a vision model already installed. The default model name is `qwen3.5-hermes:64k`.
- A legacy daily-sheet workbook or Fall 2026 monthly workbook containing `BLANK`, and JPEG/MPO, PNG, or WebP photos of its count tables.
- Local disk for the SQLite database and original evidence. Do not use SMB/NFS storage.

```bash
docker --version
docker compose version
```

Both commands must report an installed version. After startup, the application's diagnostics verify the Ollama version and model capabilities.

## Install

Download `ucac-ocr-v0.1.0.zip` from the [v0.1.0 release](https://github.com/willtheorangeguy/ucac-ocr/releases/tag/v0.1.0). Extract it into a new directory. The ZIP contains `compose.yaml` and `.env`. Set these values in `.env` for Ollama running on the Docker host:

```dotenv title=".env — inference settings"
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3.5-hermes:64k
```

For another server, use its reachable LAN URL and exact installed model name. See [Installation](installation.md) for source builds and registry authentication errors.

## First run

1. From the extracted directory, start both services:

    ```bash
    docker compose up -d
    docker compose ps
    ```

    Expect `web` and `worker` to reach `healthy`. Database setup runs automatically.

2. Check model readiness:

    ```bash
    docker compose exec web python -m app.cli diagnostics
    ```

    A successful command prints JSON containing `version`, `model`, `capabilities`, and a model `digest` when available. `capabilities` must contain `vision`. If the command fails, follow [Troubleshooting](troubleshooting.md).

3. Check the web process:

    ```bash
    curl --fail http://localhost:8000/health
    ```

    Expected body:

    ```json
    {"web":"ok"}
    ```

4. Open the [local application](http://localhost:8000). Choose a month, upload the supported workbook, and select **new-month** to reset only that month's exported inputs or **continuation** to retain its existing inputs.
5. Add photos or a ZIP. Select **New printed** for revised paper forms or **New monthly** for monthly-form photos. Start the import.
6. Inspect detected boxes. For uncertain boxes, click top-left, top-right, bottom-right, bottom-left around all seven columns of count rows, excluding the header. The fourth click saves the selection.
7. Wait for OCR, fix flagged images, and download `YYYY-MM-headcounts.xlsx`. Inspect `IMPORT REPORT` for unresolved cells and missing coverage. Blank and numeric zero remain distinct.

## What just happened

Web saved the uploaded workbook and photos to the persistent `pool-data` volume. The worker generated table crops, sent them sequentially to your Ollama server, reconciled counts, and exported a revisioned workbook. Closing the browser does not stop it. Missing or unresolved counts export as blanks, with their issues recorded in the report.

## Next steps

Read [Usage](usage.md) for review controls, [Configuration](configuration.md) for stricter profiles, and [Deployment and recovery](deployment.md) for pausing, upgrades, backup, and restore. Keep Docker running and retain the volume.
