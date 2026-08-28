# CI repository setup

Repository files define the workflows, but the following settings must be
created by an organization or repository administrator.

## Repository Variables

Configure the following Repository Variables in GitHub Settings. Runner values
are JSON arrays, not comma-separated strings. Set the custom labels to the
labels actually registered on the target runners; the `a`/`p` labels in
runner-local configuration are canonical aliases,
not assumptions made by the workflows. `llm_vlm` resolves to `CI_RUNNER_A` and
`embodied` resolves to `CI_RUNNER_P`; each suite runner builds its own local
candidate image when `--build-image` is requested.

- `CI_RUNNER_A`: JSON label array for the A-card regression runner.
- `CI_RUNNER_P`: JSON label array for the P-card regression runner.
- `CI_REVIEW_RUNNER`: JSON label array for the Claude review runner.
- `CI_ENABLE_LLM_VLM`: `true` only when the A-card suite is provisioned;
  otherwise `llm_vlm` dispatch is intentionally rejected.
- `DOCKERHUB_IMAGE`: release image name, for example `loongforge/loongforge`.

Configure these Claude review repository variables:

- `CLAUDE_REVIEW_MODEL` is required and must be a model ID accepted by the
  configured `ANTHROPIC_BASE_URL`.
- `CLAUDE_CODE_EXECUTABLE` may point to a pinned Claude Code binary already
  installed on every selected review runner. When set, the action skips its
  network installation step. Leave it empty to use the action's automatic
  installation.

When a review fails, the workflow prints only SDK result metadata
(`api_error_status`, `terminal_reason`, turn count, and timing). The full
`claude-execution-output.json` contains model/tool content and remains in the
runner temp directory only; do not upload it or print it to public logs.

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

Remove obsolete `INTERNAL_CI_*` variables after the old internal CI workflow
has been retired. They are not consumed by the current workflows and may
expose runner-local paths through the public repository configuration.

Create protected `pypi-release` and `dockerhub-release` Environments for the
release workflow. Configure PyPI Trusted Publishing (OIDC) in the former, and
`DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` secrets plus approval protection in the
latter. The repository's release workflow does not move Docker Hub's `latest`
tag.

## Runner labels

- A-card regression runner: `self-hosted`, plus the registered A-card custom
  label (the example alias is `a`).
- P-card regression runner: `self-hosted`, plus the registered P-card custom
  label (the example alias is `p`).
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

Create the `baidu-baige/loongforge-maintainers` Team before activating the
`.github/CODEOWNERS` rule. The repository should use a `master-protection`
Ruleset requiring one non-author Code Owner approval, resolved conversations,
an up-to-date branch, and the `ci-gate` check. Use a separate
`release-tag-protection` Ruleset for immutable `v*` tags.

Keep the default `GITHUB_TOKEN` permission read-only and require approval for
first-time fork workflows. Because this repository uses self-hosted runners,
only trusted dispatch workflows should reach those runners. The current
repository allows all third-party Actions and does not require SHA pinning;
enable mandatory pinning only after every `@vN` reference has been replaced by
an audited full commit SHA.

Docker Hub releases publish only the validated version tag. Do not configure
release automation that implicitly moves `latest`.

The repository currently has no post-merge workflow that promotes a validated
candidate image to the internal registry or updates the Runner default image.
Until that workflow is added, perform the promotion manually only after
checking the merged PR, required Checks, source tree SHA, and candidate image
revision; keep registry write credentials out of PR jobs.
