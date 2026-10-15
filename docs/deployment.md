# Pool Headcount — Deployment and Recovery

Use [installation](./installation.md) for initial setup and [configuration](./configuration.md) for settings. These examples use the published Compose file; source builds must include `-f compose.yaml -f compose.build.yaml` consistently.

## Service lifecycle and health

```sh
docker compose up -d
docker compose ps
docker compose logs --tail=100 web worker
docker compose exec web python -m app.cli diagnostics
docker compose exec worker python -m app.cli worker-health
```

Web publishes port 8000 to `127.0.0.1:8000` by default. Its `/health` check queries SQLite; worker health checks its independent database heartbeat. A heartbeat is recent when younger than `max(60, HEARTBEAT_INTERVAL * 4)` seconds. Neither check establishes correct OCR or current Ollama availability. The worker starts after web health succeeds, and both use `restart: unless-stopped`.

For direct source processes, run the same CLI commands with the installed interpreter. The simplified report page omits batch management controls; use CLI/API pause and status.

## Persistence and safe stopping

Both services mount the same named `pool-data` volume at `/data`. Ordinary container recreation and `docker compose stop` retain it. `docker compose down -v` deletes it and must only be used when intentional data destruction is acceptable. Keep SQLite on local disk rather than network shares.

Pause **every** active batch, then inspect status until no task is `in_flight`:

```sh
docker compose exec web python -m app.cli pause JOB_ID
docker compose exec web python -m app.cli status JOB_ID
docker compose stop
```

Do not mistake a pause request for immediate cancellation of the active model call. Forced shutdown remains recoverable, but unfinished inference must retry after cooldown. Resume paused jobs explicitly after maintenance.

## Upgrade

Back up first. For published deployments, change `POOL_HEADCOUNT_IMAGE` in `.env` to the desired release, then:

```sh
docker compose pull
docker compose up -d
docker compose ps
```

For source builds, update the checkout and use the build override with `up -d --build`. Startup applies migrations. Settled legacy exports queue a new monthly revision without repeating OCR; paused jobs remain paused. Preserve the previous image tag and backup together; older code is not guaranteed to understand a database written by newer code.

## Backup

Pause all batches and wait for active tasks. Run backup from the running web container with an external mount:

```sh
docker compose run --rm --no-deps -v /host/backups:/backups web \
  python -m app.cli backup /backups/backup-2026-10-15
```

Replace `/host/backups` with a real absolute host directory writable by container UID 10001. Choose a destination that does not already exist. Use suitable permissions for the host directory.

For a source deployment:

```sh
python -m app.cli backup /path/outside/data/backup-2026-10-15
```

The CLI uses SQLite's consistent backup API and copies all referenced immutable artifacts, including optional recalculated exports. `restore.json` records the original absolute data directory. An active partial response is not stable, which is why pausing first matters. Retain the backup as a unit; a database alone omits original evidence and exports.

## Restore

1. Stop web and worker and retain the existing data/volume as a rollback copy.
2. Restore the entire backup into a **fresh** data directory. Preserve relative paths and ensure the runtime user can write it. For source deployments, use the same absolute `DATA_DIR` recorded in `restore.json`.
3. For Compose, populate a fresh Docker volume with the backup contents at its root and mount that volume at `/data` for both services. For example, after manually creating and populating `pool-data-restored`, an override can select it:

```yaml
volumes:
  pool-data:
    external: true
    name: pool-data-restored
```

4. Check that the backup originally used `/data` before starting this Compose restore. Restore contents must be accessible to UID 10001. Start web first to migrate, inspect status, then start the worker.
5. Review diagnostics and resume deliberately paused jobs. The next worker recovers abandoned attempts; do not mix a restored database with a newer set of inputs.

There is no automated path-rebasing restore command. Moving between different absolute paths requires rewriting artifact references in jobs, sources, pages, tasks, attempts, exports, and recalculated report metadata on a copy, then validating that copy. An image rollback alone does not undo schema/data changes.

## LAN access

The app has no user accounts or authorization boundaries between batches, evidence files, and controls. Put LAN exposure behind an access-controlled reverse proxy. Configure `BIND_ADDRESS` deliberately and set a proxy upload body limit consistent with batch limits. Use a direct reachable Ollama address; the inference client bypasses environment HTTP proxies and needs long read deadlines. Avoid proxies that terminate slow streaming calls.

## Logs and capacity

Worker logs are written to `DATA_DIR/worker.log`, rotating at 5 MB with four backups, and to service output. Per-attempt streams are bounded by `MAX_RESPONSE_BYTES`. Originals, reviews, response evidence, and export history are retained indefinitely. Monitor free disk space and back up before any manual retention cleanup; there is no automatic purge command.
