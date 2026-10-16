# Configuration

## Precedence

Process environment variables override `.env`, which overrides defaults in [Settings](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/app/config.py). The file is loaded from the process working directory. Uppercase the Python field name to form the environment variable. There is no prefix or general CLI setting override. Both web and worker must use the same settings and data directory. Restart both after changes.

Unknown `.env` keys are ignored by the Python settings class. Invalid typed values, invalid `VERIFICATION`, and `ROWS_PER_BAND` outside 1–12 cause startup validation errors. Free-form strings such as retry schedules and daily pause times need valid values even where the class does not validate their syntax. `/settings` displays settings and diagnostics rather than saving changes.

## Application environment variables

Defaults are Python defaults, which can differ from `.env.example`. Seconds are used for timeouts. Byte limits are decimal bytes.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `DATA_DIR` | path | `data` | SQLite, artifacts, locks, and worker log; identical for web and worker. Compose forces `/data`. |
| `OLLAMA_BASE_URL` | string | empty | Required existing HTTP(S) Ollama endpoint; use a reachable LAN URL or Docker host address. |
| `OLLAMA_MODEL` | string | `qwen3.5-hermes:64k` | Exact installed model name. |
| `NUM_CTX` | integer | `8192` | Context option sent per request. Smaller retries cap it at 8192. |
| `NUM_PREDICT` | integer | `4096` | Output token budget; smaller retries double it. |
| `TEMPERATURE` | number | `0.1` | Per-request generation temperature. |
| `PRESENCE_PENALTY` | number | `0` | Per-request presence penalty. |
| `THINK` | boolean | `false` | Request boolean thinking; preflight checks support when enabled. |
| `ROUGH_COUNTS` | boolean | `true` | Compact count extraction and approximate acceptance rules. |
| `VERIFICATION` | string enum | `off` | `off` or `always`; enables independent B crops when `always`. |
| `KEEP_ALIVE` | string | `30m` | Ollama model keep-alive request. |
| `ROWS_PER_BAND` | integer | `12` | A-pass rows per count crop; integer 1–12. B uses half, at least one. |
| `CONNECT_TIMEOUT` | number | `15` | HTTPX connection deadline. |
| `WRITE_TIMEOUT` | number | `300` | HTTPX write deadline. |
| `POOL_TIMEOUT` | number | `30` | HTTPX pool acquisition deadline. |
| `READ_TIMEOUT` | number | `3600` | Maximum silence between received chunks, not total request time. |
| `WALL_TIMEOUT` | number | `14400` | Total request watchdog; `0` disables it. Must be nonnegative. |
| `HEARTBEAT_INTERVAL` | number | `10` | Worker heartbeat interval. |
| `RETRY_DELAYS` | string | `30,120,300,900,1800` | Comma-separated retry backoff values; keep a nonempty list of numeric delays. |
| `DISCONNECT_COOLDOWN` | number | `60` | Delay after interrupted or uncertain remote termination. |
| `MAX_FILES` | integer | `500` | Batch/folder/expanded ZIP file-count bound. |
| `MAX_EXPANDED_BYTES` | integer | `2000000000` | Expanded batch and aggregate upload bound. |
| `MAX_FILE_BYTES` | integer | `50000000` | Individual file bound and uploaded template bound. |
| `MAX_RESPONSE_BYTES` | integer | `20000000` | Bound on raw response content per attempt; exceeding it fails the attempt. |
| `MAX_PIXELS` | integer | `80000000` | Decoded image width × height bound. |
| `LIBREOFFICE` | string | empty | Optional installed headless executable path for separate recalculated exports. |
| `PAUSE_START` | string | empty | Start of daily inference pause, `HH:MM` in process local time. |
| `PAUSE_END` | string | empty | End of daily inference pause; set both values. Overnight windows work. |

`OLLAMA_BASE_URL` is required for inference. For Ollama on the Docker host, use `http://host.docker.internal:11434`; for another machine, use its reachable LAN URL. `LIBREOFFICE` can be `/usr/bin/libreoffice` when that executable is installed. Daily pause examples are `PAUSE_START=08:00` and `PAUSE_END=17:00`; set both in process local time. Overnight windows work. Keep `RETRY_DELAYS` a nonempty numeric list.

The default morning page uses four requests: one date header and three count bands. Set `ROUGH_COUNTS=false` and `VERIFICATION=always` for detailed readings and independent B crops. `THINK=true` is a separate choice requiring model support. Changing settings does not reprocess successful tasks automatically. Pause, wait for active inference, and use the [refresh command](commands.md) to reinterpret saved readings.

A smaller retry caps context at 8192 and doubles the output token budget. Pause windows stop new inference dispatch, not an active call or preprocessing. The app closes a disconnected response before releasing its inference slot, but the remote generation may continue. It does not stop shared models or change Ollama's global concurrency.

## Compose variables

[Compose](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/compose.yaml) interprets these variables. Direct Uvicorn commands do not use them. A container's `localhost` refers to that container. Compose forces `DATA_DIR=/data` for both services, overriding the `.env` value.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `POOL_HEADCOUNT_IMAGE` | image reference | `ghcr.io/willtheorangeguy/ucac-ocr:0.1.0` | Same published image for both services. Release downloads pin their own version. |
| `BIND_ADDRESS` | address string | `127.0.0.1` | Host interface for the published web port. |
| `PORT` | port string | `8000` | Host web port. The container still listens on 8000. |

## Examples

This complete example uses the shipped rough profile and Ollama on the Docker host. Change the model name if your installed model differs. Blank optional strings disable their feature. `MAX_PIXELS` is supported by Settings even though it is absent from the tracked example file.

```dotenv title=".env"
# Published image. Release downloads pin this to their exact version.
POOL_HEADCOUNT_IMAGE=ghcr.io/willtheorangeguy/ucac-ocr:0.1.0
BIND_ADDRESS=127.0.0.1
PORT=8000

# Compose overrides DATA_DIR to its persistent /data volume.
DATA_DIR=data
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3.5-hermes:64k
NUM_CTX=8192
NUM_PREDICT=4096
TEMPERATURE=0.1
PRESENCE_PENALTY=0
THINK=false
KEEP_ALIVE=30m
ROWS_PER_BAND=12
CONNECT_TIMEOUT=15
WRITE_TIMEOUT=300
POOL_TIMEOUT=30
READ_TIMEOUT=3600
WALL_TIMEOUT=14400
HEARTBEAT_INTERVAL=10
RETRY_DELAYS=30,120,300,900,1800
DISCONNECT_COOLDOWN=60
MAX_FILES=500
MAX_EXPANDED_BYTES=2000000000
MAX_FILE_BYTES=50000000
MAX_RESPONSE_BYTES=20000000
MAX_PIXELS=80000000
LIBREOFFICE=
# Optional daily inference pause window, process local time (e.g. 08:00 to 17:00)
PAUSE_START=
PAUSE_END=

ROUGH_COUNTS=true
VERIFICATION=off
```

There are no application user credentials or configured Ollama authorization headers. Protect LAN exposure with an access-controlled reverse proxy. Originals and reviews are not deleted automatically; account for normalized images, crops, response streams, and all export revisions. Worker logs rotate at 5 MB with four backups. See [Deployment and recovery](deployment.md).
