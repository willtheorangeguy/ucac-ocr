# Pool Headcount — Configuration

[Settings](../app/config.py) load `.env` from the process working directory; environment variables override the file. Copy the tracked [example](../.env.example), replace its deployment-specific Ollama address, and restart both web and worker after changes. The `/settings` page displays settings and diagnostics; it is not a persistent configuration editor.

## Storage and inference

Defaults below are Python defaults, which can differ from the example deployment file.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATA_DIR` | `data` | SQLite, artifacts, locks, and worker log; identical for web and worker. Compose forces `/data`. |
| `OLLAMA_BASE_URL` | empty | Required existing HTTP(S) Ollama endpoint; use a reachable LAN URL or Docker host address. |
| `OLLAMA_MODEL` | `qwen3.5-hermes:64k` | Exact installed model name. |
| `NUM_CTX` | `8192` | Context option sent per request. Smaller retries cap it at 8192. |
| `NUM_PREDICT` | `4096` | Output token budget; smaller retries double it. |
| `TEMPERATURE` | `0.1` | Per-request generation temperature. |
| `PRESENCE_PENALTY` | `0` | Per-request presence penalty. |
| `THINK` | `false` | Request boolean thinking; preflight checks support when enabled. |
| `ROUGH_COUNTS` | `true` | Compact count extraction and approximate acceptance rules. |
| `VERIFICATION` | `off` | `off` or `always`; enables independent B crops when `always`. |
| `KEEP_ALIVE` | `30m` | Ollama model keep-alive request. |
| `ROWS_PER_BAND` | `12` | A-pass rows per count crop; integer 1–12. B uses half, at least one. |

The default profile produces four requests for a morning page: a header and three count bands. To request detailed readings and independent verification, use `ROUGH_COUNTS=false` and `VERIFICATION=always`. `THINK=true` is a separate choice. Existing successful tasks are retained; changing settings does not automatically reprocess them. To reinterpret saved readings using current count rules, pause, wait for active inference, and use `refresh JOB_ID`; see [commands](./commands.md).

## Timeouts and retry controls

Values are seconds unless stated otherwise.

| Variable | Default | Meaning |
| --- | --- | --- |
| `CONNECT_TIMEOUT` | `15` | HTTPX connection deadline. |
| `WRITE_TIMEOUT` | `300` | HTTPX write deadline. |
| `POOL_TIMEOUT` | `30` | HTTPX pool acquisition deadline. |
| `READ_TIMEOUT` | `3600` | Maximum silence between received chunks, not total request time. |
| `WALL_TIMEOUT` | `14400` | Total request watchdog; `0` disables it. Must be nonnegative. |
| `HEARTBEAT_INTERVAL` | `10` | Worker heartbeat interval. |
| `RETRY_DELAYS` | `30,120,300,900,1800` | Comma-separated retry backoff values; keep a nonempty list of numeric delays. |
| `DISCONNECT_COOLDOWN` | `60` | Delay after interrupted or uncertain remote termination. |
| `PAUSE_START` | empty | Start of daily inference pause, `HH:MM` in process local time. |
| `PAUSE_END` | empty | End of daily inference pause; set both values. Overnight windows work. |

Pause windows stop new inference dispatch, not preprocessing or a call already in progress. The client closes the response before releasing its slot, but a disconnected remote generation may continue. This app does not stop shared models or change Ollama's global concurrency.

## Limits and optional recalculation

Byte limits use decimal bytes. `MAX_PIXELS` is in the settings class but is not listed in `.env.example`; you can still set it in the environment or `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAX_FILES` | `500` | Batch/folder/expanded ZIP file-count bound. |
| `MAX_EXPANDED_BYTES` | `2000000000` | Expanded batch and aggregate upload bound. |
| `MAX_FILE_BYTES` | `50000000` | Individual file bound and uploaded template bound. |
| `MAX_PIXELS` | `80000000` | Decoded image width × height bound. |
| `MAX_RESPONSE_BYTES` | `20000000` | Bound on raw response content per attempt; exceeding it fails the attempt. |
| `LIBREOFFICE` | empty | Optional installed headless executable path for separate recalculated exports. |

Originals and reviews are not automatically deleted. Capacity planning must include normalized images, crops, response streams, and every export revision. Worker logs rotate at 5 MB with four backups.

## Compose-only variables

| Variable | Example/fallback | Meaning |
| --- | --- | --- |
| `POOL_HEADCOUNT_IMAGE` | `ghcr.io/willtheorangeguy/ucac-ocr:0.1.0` | Published image used by both services; release downloads pin it to their version. |
| `BIND_ADDRESS` | `127.0.0.1` | Host interface for the published web port. |
| `PORT` | `8000` | Host web port; container web port remains 8000. |

These variables are interpreted by [Compose](../compose.yaml), not by the Python settings class. They do not change a direct Uvicorn command. Containers receive `DATA_DIR=/data` regardless of its `.env` value. For Ollama on the Docker host, set `OLLAMA_BASE_URL=http://host.docker.internal:11434`; the provided Compose file supplies the host mapping. A container's `localhost` refers to that container.

There are no application user credentials or configured Ollama authorization headers. Protect any LAN exposure with an access-controlled reverse proxy; see [deployment](./deployment.md).
