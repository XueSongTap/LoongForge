# CI repository setup

Repository files define the workflows, but the following settings must be
created by an organization or repository administrator.

## Repository Variables

Create every variable from `.github/ci-variables.example.json`. Replace the
`P6K` label only if the registered P6K runner uses a different custom label.
The values of `CI_RUNNER_A` and `CI_RUNNER_P` are JSON
arrays, not comma-separated strings. `llm_vlm` resolves to `CI_RUNNER_A` and
`embodied` resolves to `CI_RUNNER_P`; each suite runner builds its own local
candidate image when `--build-image` is requested.

Each self-hosted runner must provide `CI_CONFIG_PATH_IMAGE` in its service
environment, pointing at that machine's private `image.env`. The service
environment and that file together must provide the values shown in
`.github/ci-config.example.env`, including the default image, isolated mounts,
and BuildKit mirror paths. Do not put registry credentials or signed source
URLs in the repository.

Each suite runner must also provide a working Docker Buildx plugin because the
PR Dockerfile uses BuildKit secrets for runner-local APT, PyPI, and source
mirrors. Verify it with `docker buildx version`; installing the CLI plugin does
not require restarting the Docker daemon.

## Runner labels

- A800 regression runner: `self-hosted`, `A800`.
- P6K regression runner: `self-hosted`, `P6K`.
- Candidate images are built on the same suite runner that performs regression.

## First activation

Enable the `ok-to-test`, `gpu-regression`, and `gpu-invalidate` workflows on the
default branch, then verify a maintainer-dispatched run on each labeled suite
runner. Confirm that the PR `ci-gate` check progresses through queued, optional
candidate build, regression, and final status. Push a second commit while a GPU
run is active and confirm that the old check becomes cancelled and the runner's
targeted cleanup removes its regression container and candidate image where
possible. Cancellation cleanup is best-effort and must not globally prune the
shared BuildKit cache.

Configure branch protection to require the PR job named `ci-gate`. A manual
dispatch ends in `manual-ci-gate` and is intended only for diagnostics; it must
not satisfy the PR requirement.

Docker Hub releases publish only the validated version tag. Do not configure
release automation that implicitly moves `latest`.
