# Pool Headcount

Pool Headcount (`ucac-ocr`) turns handwritten pool attendance photos into monthly Excel workbooks. A local FastAPI web app and durable worker use your existing Ollama vision server, retain original evidence, and let you correct uncertain counts before downloading a workbook. The default profile favors approximate counts. Whole-month OCR accuracy remains unmeasured.

## Key features

- Upload JPEG/MPO, PNG, WebP, or ZIP batches and skip Live Photo MOV companions.
- Detect table boxes and correct uncertain grids with four corner clicks.
- Read counts, integer addition, blanks, and copy-down marks.
- Recover unfinished tasks after interruption without repeating successful work.
- Preserve reviewed decisions, provenance, and immutable export revisions.
- Export legacy and Fall 2026 inputs to Public/External/Internal/Dry monthly columns.

## Quick start

Download and extract the [v0.1.0 deployment ZIP](https://github.com/willtheorangeguy/ucac-ocr/releases/tag/v0.1.0). Set `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in its `.env`, then start the services:

```bash
docker compose up -d
```

Open the [local application](http://localhost:8000), upload a supported workbook and photos, review flagged images, and download the latest workbook. Follow [Getting started](getting-started.md) for prerequisites and verification.

## Where to next

<div class="wt-grid" markdown>

[:material-rocket-launch: **Getting started**<br>Install and produce a first workbook](getting-started.md){ .wt-card }

[:material-download: **Installation**<br>Published containers and source methods](installation.md){ .wt-card }

[:material-tune: **Configuration**<br>Inference profiles, limits, and storage](configuration.md){ .wt-card }

[:material-table: **Usage**<br>Table boxes, count review, and downloads](usage.md){ .wt-card }

[:material-sitemap: **Architecture**<br>Components, schema, and durable recovery](architecture.md){ .wt-card }

[:material-api: **API**<br>HTTP routes and request examples](api.md){ .wt-card }

</div>

The site describes this source checkout. A published image may have an earlier feature set. The [validation record](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/VALIDATION.md) preserves historical measurements. The [implementation plan](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/IMPLEMENTATION_PLAN.md) records older design choices superseded by current [count and workbook rules](rules.md).

## Support

Report reproducible problems in [GitHub Issues](https://github.com/willtheorangeguy/ucac-ocr/issues). Include the deployment version, diagnostic, and reproduction steps without private attendance evidence.
