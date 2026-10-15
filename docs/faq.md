# Pool Headcount — FAQ

## Does the app install Ollama or change my model?

No. It connects to an existing configured HTTP(S) endpoint and supplies per-request options. It does not change global Ollama settings, stop shared models, or configure server parallelism. Other clients may still compete for inference resources.

## Where do photos go?

Originals, normalized images, crops, streams, decisions, and exports remain in `DATA_DIR`. OCR crops are sent to the configured Ollama server. The app does not integrate a cloud OCR service. A remote Ollama endpoint still receives those crops, so choose its location deliberately.

## How accurate is it?

No whole-sheet or whole-month accuracy percentage has been established. The default rough profile prioritizes approximate counts and accepts readable corrections and likely blanks. Review flagged cells and spot-check accepted results. Detailed readings with independent verification are optional. The [testing guide](./testing.md) distinguishes regression tests from live accuracy evidence.

## Why can it be slow?

One worker dispatches one request at a time. Model size, context, thinking, hardware, competing clients, and streaming behavior all affect duration. A long read deadline is intentional. Current default morning processing uses four calls; historical detailed A/B profiles needed more calls. Recorded single-crop timings are not a month throughput promise.

## Can I close the browser or restart the app?

Yes. Work is persisted independently of the browser. Restarting recovers unfinished tasks and preserves completed ones, subject to cooldown after uncertain remote termination. Keep the data directory/volume intact. See [deployment](./deployment.md) before stopping or restoring.

## Why is my workbook provisional when no individual count is flagged?

The batch can still lack dates or sections. Review `IMPORT REPORT`, then acknowledge coverage through the CLI/API only when missing periods truly have no source or are not applicable. Coverage acknowledgement creates no attendance values.

## Why did my old workbook produce a new monthly layout?

All current exports use the Fall 2026 monthly `BLANK` layout. Legacy User Group + Coaches becomes Internal, while External stays blank. The stored/API key `group` still represents Internal for compatibility. See [rules](./rules.md).

## Will correcting a count run OCR again?

No. Review decisions regenerate an export revision without inference. Date-only assignment can reuse readings. Explicit source reprocessing or geometry changes create new versioned work. Reviewed cells remain protected from automatic overwrites.

## Can Excel formulas be trusted before opening the file?

The app writes date/time/count inputs explicitly and requests recalculation on open, but Python does not evaluate LET/FILTER summaries. Independent expected averages are in `IMPORT REPORT`. Optional LibreOffice produces a separate checked artifact; native rendering and successful recalculation remain unverified in the historical record.

## Can several people use it over a LAN?

There are no user accounts or per-user permissions. LAN exposure needs an access-controlled reverse proxy. Run only one worker per data directory and keep SQLite on local disk. See [deployment](./deployment.md).
