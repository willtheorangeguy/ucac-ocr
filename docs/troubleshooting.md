# Troubleshooting

Collect status and the job diagnostic before retrying. These examples assume a running Compose deployment; use the virtual environment interpreter for source installs.

```sh
docker compose ps
docker compose logs --tail=100 web worker
docker compose exec web python -m app.cli status JOB_ID
docker compose exec web python -m app.cli diagnostics
```

## Images cannot be pulled from GHCR

If pulls are denied, check the image name/tag and package visibility. Public packages allow anonymous pulls. For a private package, use a GitHub personal access token (classic) with `read:packages` and access to that package, entered at Docker's prompt:

```sh
docker login ghcr.io --username YOUR_GITHUB_USERNAME
```

A package owner can change visibility in [package settings](https://github.com/users/willtheorangeguy/packages/container/ucac-ocr/settings). Repository visibility does not establish package visibility. Re-run `docker compose pull` after fixing access.

## `waiting_for_ollama` or connection failures

Check diagnostics from inside the application environment. Set `OLLAMA_BASE_URL` to a reachable HTTP(S) endpoint; container `localhost` does not address the host. Use `http://host.docker.internal:11434` for Ollama on the Docker host or a real LAN address for another machine. Check network/firewall rules and whether the server is running. The client bypasses environment proxies.

Availability failures retain tasks and back off; after five failures, health probes gate retries. A healthy `/api/version` does not establish that a disconnected generation has ended. Avoid repeatedly forcing retries during an outage.

## Batch paused with a model/configuration diagnostic

Preflight requires Ollama 0.17.1 or later, an installed model with vision, and thinking support if `THINK=true`. Correct the URL/model/options, restart both services after `.env` changes, then use `resume JOB_ID`. Permanent HTTP/model errors pause instead of consuming endless content retries.

## Web is healthy but nothing processes

The web service only accepts/reviews work. Check the separate worker heartbeat and logs. Ensure both processes use the same `DATA_DIR`, the job is resumed, and the daily pause window is not active. Web health does not check model connectivity.

`Another worker owns the data directory` means the OS lock is held. Stop the duplicate worker rather than deleting a lock while its owner may still be running. Do not share one data directory between independent workers.

## Table detection fails or layout is wrong

Select the correct photo and retry automatic detection. If necessary, mark all seven columns and only count rows in clockwise order from top-left. Exclude the header. Check 31 morning, 36 afternoon, or 67 full-day rows; incomplete grids can remain rejected. Choose **New printed** explicitly for revised paper forms and **New monthly** for partial monthly sections.

`This photo changed during detection` means a concurrent update saved newer geometry; reload the saved box and retry. `Pause and wait for active request before changing source` means inference must checkpoint first. Restarting with an improved detector retries unresolved older geometry failures once while retaining manual corners and pauses.

## Photos or ZIPs are rejected

Supported formats are JPEG/MPO, PNG, and WebP. Convert unsupported formats before upload; MOV companions are skipped, and MOV-only selections contain no usable photos. Check `MAX_FILES`, `MAX_FILE_BYTES`, `MAX_EXPANDED_BYTES`, and `MAX_PIXELS`. Unsafe ZIP paths/symlinks are rejected even for skipped movie entries. Corrupt photos are retained as source issues. Add corrected replacements rather than deleting originals from storage.

## Date, counts, or continuation need attention

`Date outside selected month` requires matching the selected batch month. Conflicting recognized dates need explicit `confirm:true` in source configuration and are audited. `Continuation requires daily sheets in selected month` means existing legacy daily sheets belong to another month; use the correct workbook/month or deliberately start new-month. Monthly workbooks also reject a selected entry sheet whose stored dates disagree with the chosen month.

Unreadable/conflicting cells require a numeric or blank decision; acknowledgement is not a replacement for a cell value. `Reviewer name required` needs a nonempty reviewer. For missing predecessors on copy-down, correct the preceding cell before the dependent mark. See [usage](./usage.md).

## Truncated, malformed, oversized, or resource-failed responses

The app rejects incomplete/invalid output, shifted rows, and streams exceeding `MAX_RESPONSE_BYTES`. Content failures use retries and smaller bands; exhausted work is deferred for review. Resource failures try reduced context/smaller bands. Review model diagnostics and use `retry JOB_ID` after addressing the cause. Do not treat a raw partial stream as accepted counts.

`READ_TIMEOUT` limits silence between chunks; `WALL_TIMEOUT` bounds total elapsed request time. Increase limits only when justified by observed inference behavior.

## Export fails or summaries look stale

Export failures use `awaiting_review` and a diagnostic. Check disk space, file permissions, and template integrity, then run `export JOB_ID` independently of OCR. `Immutable template checksum changed` indicates stored evidence was modified; recover the original from a consistent backup rather than editing the hash to bypass the check.

Excel formulas are not evaluated by Python. Open the workbook in a compatible spreadsheet application and inspect `IMPORT REPORT`. Optional recalculation requires `LIBREOFFICE` to point to an installed headless executable; the container does not include it. Recalculation failure retains the original artifact.

## Calibration fails before sending its b requests

The default `VERIFICATION=off` profile creates no B tasks, while the calibration script expects them. Use the explicit detailed/verification profile and isolated data directory in [testing](./testing.md). The underlying defect is recorded in [known issues](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/docs/internal/known-issues.md).

## Restore cannot find artifacts

Restore the database and its referenced files together, at the original absolute data path recorded in `restore.json`. There is no automatic path rebasing. See [deployment](./deployment.md) before attempting metadata migration on a copy.
