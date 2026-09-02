# GitHub Actions Workflows

This directory contains the CI/CD workflows for LoongForge.

## Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci-gate.yml` | PR + workflow dispatch | Run and summarize all blocking CPU checks |
| `workflow-lint.yml` | Reusable workflow | Validate GitHub Actions expressions, YAML, and CI helper contracts |
| `pr-title.yml` | Reusable workflow | Validate PR title format: `[<modules>] <type>: <description>` |
| `license.yml` | Reusable workflow | Check SPDX Apache-2.0 header on newly added source files |
| `secrets.yml` | Reusable workflow | Scan PR commits for leaked secrets via gitleaks |
| `lint.yml` | Reusable workflow | Run Ruff on changed Python files |
| `sensitive.yml` | Reusable workflow | Scan tracked files for internal identifiers via `ci/sensitive_scan.py` |
| `build.yml` | Reusable workflow | Build sdist + wheel and run Python 3.12 import smoke |
| `submodule-sync.yml` | repository dispatch / workflow dispatch + manual | Sync `third_party/Loong-Megatron` to its tracked branch and push the submodule pointer update |
| `auto-label.yml` | Issue/PR open/edit | Auto-label issues and PRs by keyword matching |
| `ok-to-test.yml` | Maintainer issue comment | Validate and dispatch `/ok-to-test` GPU regression |
| `gpu-regression.yml` | Workflow dispatch | Run exact-SHA baseline regression for one model suite |
| `gpu-invalidate.yml` | PR synchronize | Cancel stale suite GPU work after a new commit |
| `release.yml` | Version tag `vX.Y.Z` | Publish PyPI package and Docker Hub release image |

Pull requests run `ci-gate.yml` automatically. Its manual dispatch is diagnostic:
PR-only checks skip where appropriate and the final job is named
`manual-ci-gate`, so it cannot satisfy the required PR `ci-gate` check.
Operational workflows such as `submodule-sync.yml` may retain their own
dispatch inputs.

## GPU Regression

Maintainers can request a baseline regression by commenting on a pull request:

```
/ok-to-test --suite llm_vlm|embodied [--model model1,model2] [--build-image]
```

The suite selects both the test collection and its self-hosted runner:
`llm_vlm` runs on a and `embodied` runs on p. The `embodied` suite is enabled
by default; `llm_vlm` requires a registered runner and
`CI_ENABLE_LLM_VLM=true` in the workflow environment. With `--build-image`, that
same runner builds the PR's Dockerfile and immediately runs regression against
the local candidate image. Without it, regression uses the runner's configured
default image. Explicit models must belong to the selected suite and have a
baseline. New commits invalidate previous results.
The PR `ci-gate` check reports whether GPU work is queued, building a candidate
image, running regression, cancelled, passed, or failed. A new PR commit
cancels the older running or queued job for each suite, including an in-flight
candidate build or regression. Runner cleanup is targeted and best-effort:
temporary build contexts, regression containers, and candidate image tags are
removed where possible, while shared BuildKit caches are not globally pruned.
The workflow points `LOONGFORGE_REGRESSION_RUNNER` at the trusted base-branch
checkout; direct execution of a PR-provided runner hook is rejected inside
GitHub Actions.

## Releases

Version tags publish the validated Python package and only the matching
immutable Docker image tag (for example, `1.2.3`). The release workflow does
not move Docker Hub's `latest` tag.

Operator hook contracts:

- `LOONGFORGE_REGRESSION_RUNNER --source DIR --suite llm_vlm|embodied --sha SHA [--model LIST] [--candidate-revision REV]`
- `LOONGFORGE_IMAGE_BUILDER --source DIR --target a|p --sha SHA --pr NUMBER --tree-sha SHA`; stdout must contain only the local candidate image reference

The builder reads `CI_CONFIG_PATH_IMAGE` (or the wrapper's `CI_CONFIG_PATH`) from
the selected suite runner. It uses the Dockerfile's `BASE_IMAGE` build argument
and runner-local BuildKit secrets for APT, PyPI, and source mirrors. Candidate
images are tagged locally with the PR number, head SHA, tree SHA, target, and
candidate revision; this workflow never pushes or promotes them.

Repository Variables are configured in GitHub Settings. The workflow expects
`CI_RUNNER_A`, `CI_RUNNER_P`, `CI_REVIEW_RUNNER`, and
`CLAUDE_REVIEW_MODEL`; `CLAUDE_CODE_EXECUTABLE` is optional. Every self-hosted
runner provides its own `CI_CONFIG_PATH_IMAGE` environment variable; this is
not a Repository Variable because runner filesystem roots may differ.

Hooks must return nonzero on failure and must not print credentials, signed
source URLs, runner-local filesystem paths, or physical accelerator details to
the GitHub Actions log.

## PR Title Convention

```
[<modules>] <type>: <description>
```

**Modules:** `llm, vlm, vla, diffusion, train, data, ops, ckpt, peft, docker, xpu, ci, docs, tests, scripts, release`

**Types:** `feat, fix, refactor, perf, docs, test, chore, ci`

**Example:** `[llm, ckpt] feat: support Qwen3-Next checkpoint conversion`

## Adding a New Workflow

1. Create a `.yml` file in this directory.
2. Set `permissions` to least-privilege (default: `contents: read`).
3. Add a `concurrency` block to cancel stale runs on PR branches.
4. Test locally where possible before pushing.

## Submodule Sync

`submodule-sync.yml` updates `third_party/Loong-Megatron` to the branch configured in `.gitmodules` and commits the submodule pointer when it changes.

The workflow defaults to `master`. It can also receive `submodule_repository` from workflow inputs or `repository_dispatch` payloads to test against a forked Loong-Megatron without changing `.gitmodules`.

Required secrets:

- `SUBMODULE_SYNC_APP_ID`
- `SUBMODULE_SYNC_APP_PRIVATE_KEY`

The GitHub App behind those secrets must be able to push to the configured target branch. This workflow is separate from the PR `CI Gate` and is not a required merge check.
