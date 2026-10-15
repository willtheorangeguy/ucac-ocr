# Pool Headcount — Quickstart

This path uses the published `v0.1.0` deployment bundle. You need Docker with Compose, an existing Ollama server with a vision model, a supported headcount workbook, and photos of its count tables. It does not install Ollama or download a model.

## Start the services

1. Download `ucac-ocr-v0.1.0.zip` from the [v0.1.0 release](https://github.com/willtheorangeguy/ucac-ocr/releases/tag/v0.1.0) and extract it into a new directory. The archive contains `compose.yaml` and `.env`.
2. Open `.env` in an editor. Set `OLLAMA_BASE_URL` to your server's HTTP(S) address and `OLLAMA_MODEL` to its installed vision model name. The supplied name is `qwen3.5-hermes:64k`. For Ollama on the Docker host, use `http://host.docker.internal:11434`.
3. In the extracted directory, run:

```sh
docker compose up -d
docker compose ps
docker compose exec web python -m app.cli diagnostics
```

Both services should become healthy. Diagnostics should report the configured model and vision capability. Open <http://localhost:8000>. If the image cannot be pulled or diagnostics fail, use [troubleshooting](./troubleshooting.md).

## Produce a workbook

1. Choose the intended month and upload the legacy daily-sheet workbook or the Fall 2026 workbook containing the monthly `BLANK` sheet.
2. Select **new-month** to replace only that month's inputs in the exported workbook, or **continuation** to retain existing inputs for that month. The uploaded original is retained.
3. Add supported photos or a ZIP. Select the photo layout: use **New printed** for the revised paper form or **New monthly** for monthly-form photos.
4. Start the import. Review the automatically detected table boxes. If a box needs correction, click around all seven columns of count rows in top-left, top-right, bottom-right, bottom-left order, excluding the header.
5. Wait for OCR, correct flagged images, and download the latest `YYYY-MM-headcounts.xlsx`. Check the `IMPORT REPORT` for unresolved or missing coverage; blanks are distinct from numeric zero.

Closing the browser leaves processing running. Keep Docker running and retain the `pool-data` volume. For recovery, review details, and backups, continue with [usage](./usage.md) and [deployment](./deployment.md).
