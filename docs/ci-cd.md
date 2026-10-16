# CI/CD

The repository publishes release containers and uses the shared MkDocs workflows to validate and deploy documentation.

## Workflows

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `publish-container.yml` | GitHub release published | Test, publish AMD64/ARM64 images, and attach deployment assets. |
| `docs.yml` | Push to `main`/`master` affecting docs, overrides, config, caller, or listed root files; manual dispatch | Strict build and GitHub Pages deployment. |
| `docs-lint.yml` | Pull request affecting docs, overrides, config, or lint caller; manual dispatch | Markdown style, strict build, and external link checks. |

The caller files delegate documentation build logic to [willtheorangeguy/mkdocs](https://github.com/willtheorangeguy/mkdocs). They grant permissions and select the shared workflow. Theme, dependencies, and lint rules remain centralized.

## Documentation deployment

The `Docs` caller (`.github/workflows/docs.yml`) invokes `docs-build.yml@main`. It checks out the project and shared repo, installs the shared toolchain, stages the design system, and builds strictly. The resulting artifact deploys to `https://williamvdg.me/ucac-ocr/` after the first successful deployment. Deployment needs Pages enabled with GitHub Actions as the source and `pages:write`/`id-token:write` permissions.

The site owns the Pages root. The FastAPI application remains a separately hosted service. There is no static application at the Pages root to preserve.

## Pull request checks

The `Docs Lint` caller (`.github/workflows/docs-lint.yml`) invokes the shared `docs-lint.yml@main`. A failure identifies Markdown style, a strict build problem, or an unreachable link. Run the same strict build locally before pushing:

```bash
../mkdocs/scripts/docs-serve.sh --build
```

Use the separate documentation environment described in [Development](development.md). Generated design assets are ignored and must not be committed. Internal notes and the writing standard are excluded from the published site.

## Release process

[Publish release container](https://github.com/willtheorangeguy/ucac-ocr/blob/HEAD/.github/workflows/publish-container.yml) runs when a GitHub release is published, rather than on every source push or pull request. It:

1. Checks out the release tag and generates version-pinned deployment files.
2. Builds a Linux AMD64 test image and runs pytest with the checkout mounted read-only.
3. Publishes Linux AMD64/ARM64 images to `ghcr.io/willtheorangeguy/ucac-ocr` using `GITHUB_TOKEN` with package-write permission.
4. Starts the published image with standalone Compose and waits for service health.
5. Attaches `compose.yaml`, `default.env`, and the ZIP preserving `.env`, then cleans up the temporary smoke-test volume.

The generator accepts `vMAJOR.MINOR.PATCH` with an optional prerelease suffix. Stable `v0.1.0` publishes `0.1.0`, `v0.1.0`, `0.1`, and `latest`; prereleases do not update minor/latest tags. Attachments come from `.env.example`, never an operator's `.env`.

Generate deployment files locally without publishing:

```bash
python scripts/prepare_release.py v0.1.0 ghcr.io/willtheorangeguy/ucac-ocr /tmp/ucac-release-files
```

Keep generated output outside the checkout. The standalone service health check does not establish live OCR accuracy or GPU performance.
