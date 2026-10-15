<!-- Logo -->
<h1 align="center">Pool Headcount</h1>

<!-- Tagline -->
<h4 align="center">A local application for turning handwritten pool attendance photos into monthly Excel workbooks.</h4>

<!-- Badges -->
<div align="center">
  <img alt="Publish release container" src="https://github.com/willtheorangeguy/ucac-ocr/actions/workflows/publish-container.yml/badge.svg">
  <img alt="GitHub Issues" src="https://img.shields.io/github/issues/willtheorangeguy/ucac-ocr">
  <img alt="GitHub Pull Requests" src="https://img.shields.io/github/issues-pr/willtheorangeguy/ucac-ocr">
  <img alt="License: MIT" src="https://img.shields.io/github/license/willtheorangeguy/ucac-ocr">
  <img alt="Latest release" src="https://img.shields.io/github/v/release/willtheorangeguy/ucac-ocr">
</div>

<!-- Nav -->
<p align="center">
  <a href="#key-features">Key Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#support">Support</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#license">License</a>
</p>

`ucac-ocr` runs a FastAPI web application and a separate durable worker against
an existing Ollama vision model. It retains originals, OCR attempts, review
choices, and export revisions in a local data directory and SQLite database.

The default profile favors approximate headcounts and short, single-pass OCR.
Human review and spot checks remain necessary: a whole-month accuracy rate has
not been established. The app has no user accounts and binds to localhost by default.

## Key Features

- Import photos or ZIPs, including iPhone JPEG/MPO images; skip Live Photo MOV clips.
- Detect perspective table boxes, with four-click correction for uncertain grids.
- Read handwritten counts, addition, blanks, and copy-down marks with a configurable Ollama model.
- Resume unfinished work after interruptions without repeating successful tasks.
- Review conflicting readings and preserve numeric zero separately from blank cells.
- Export legacy or Fall 2026 inputs into the monthly Public/External/Internal/Dry layout.
- Keep immutable workbook revisions, provenance, and consistent database backups.

## Installation

Install Docker with Compose and have an Ollama vision server available. Download
and extract `ucac-ocr-v0.1.0.zip` from the
[release](https://github.com/willtheorangeguy/ucac-ocr/releases/tag/v0.1.0).
Edit the extracted `.env` to set `OLLAMA_BASE_URL` and `OLLAMA_MODEL`, then run:

```sh
docker compose up -d
```

Open <http://localhost:8000>. See the [quickstart](docs/quickstart.md) for checks
and [installation](docs/installation.md) for source and Windows options.

## Usage

Choose a month, upload a supported workbook and photos, select the workbook mode
and photo layout, then start the import. Check table boxes, correct flagged
images, and download `YYYY-MM-headcounts.xlsx` when processing settles.
Closing the browser does not stop the worker. Missing or unresolved counts stay
blank and appear in the workbook's import report.

## Documentation

Full documentation lives in [`docs/`](docs/README.md):
[Installation](docs/installation.md) · [Usage](docs/usage.md) · [Configuration](docs/configuration.md) · [Troubleshooting](docs/troubleshooting.md)

## Support

File an [issue](https://github.com/willtheorangeguy/ucac-ocr/issues/new/choose).

## Contributing

Contributions welcome. See the org-wide [Contributing Guide](https://github.com/willtheorangeguy/.github/blob/main/CONTRIBUTING.md) and [Code of Conduct](https://github.com/willtheorangeguy/.github/blob/main/CODE_OF_CONDUCT.md).

## License

MIT — see [`LICENSE.md`](LICENSE.md).
