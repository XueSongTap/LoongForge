# CI Correctness Hardening Design

## Context

PR #151 refactors the CPU gate, GPU regression dispatch, candidate-image build,
Claude review, and release workflows. The workflows pass their current lint and
unit checks, but review identified several event-semantics and trust-boundary
problems that those checks do not exercise.

This change hardens the confirmed problems while preserving the current CPU
gate shape and the two suite-specific GPU jobs. Runner-local BuildKit secrets
remain unchanged because candidate-image builds require explicit maintainer
approval and secret isolation is outside this change's agreed scope.

## Goals

- Keep the seven CPU checks and the required `ci-gate` check unchanged for PRs.
- Prevent manual workflow dispatch from satisfying the required PR check.
- Reject PR titles with no module or duplicate modules.
- Aggregate only the newest CPU check run for each expected check name.
- Cancel stale GPU build/regression jobs immediately when a PR receives a new
  commit.
- Complete a cancelled GPU check without waiting for CPU polling.
- Prevent Claude review from loading PR-controlled project settings and hooks.
- Make the Docker Hub release build use the context layout expected by the
  Dockerfile.
- Publish immutable version tags only; do not update `latest` automatically.
- Add regression tests for title validation and check-run selection.

## Non-goals

- Changing how runner-local BuildKit secrets are supplied.
- Merging the duplicated `llm_vlm` and `embodied` GPU jobs.
- Enabling the temporarily unavailable `llm_vlm` suite.
- Renaming the required PR `ci-gate` check or changing branch protection.
- Forcing release builds to use a source manifest before a complete manifest is
  available.
- Globally pruning BuildKit caches on shared self-hosted runners.

## Design

### Testable CI helpers

Move the pure PR-title and check-run-selection logic out of inline workflow
JavaScript into small CommonJS modules under `.github/scripts/`. GitHub Script
steps will import the modules after checkout, while Node's built-in test runner
will exercise the same production functions without additional dependencies.

The title validator will preserve the documented title format and accepted
types/modules, and additionally reject an empty normalized module list and
duplicate modules.

The check selector will group API results by expected logical check name, sort
matching runs by `started_at` (falling back to `created_at`), and retain only the
newest run. Both the polling termination condition and the success decision
will use this selected set. An older success cannot mask a newer queued,
in-progress, cancelled, or failed run.

### CPU gate event semantics

The PR path retains the displayed final job name `ci-gate`. A manual dispatch
uses `manual-ci-gate`, so skipped PR-only checks cannot accidentally satisfy a
required PR status. Documentation will state that manual dispatch validates
only checks applicable outside a pull-request event.

### Stale GPU cancellation

Concurrency moves from the entire GPU workflow to the suite-specific runner
jobs. The group keys become:

```text
gpu-regression-<pr-number>-llm_vlm
gpu-regression-<pr-number>-embodied
```

They intentionally omit the head SHA. A trusted `pull_request_target` workflow
listening for `synchronize` creates one lightweight invalidation job per suite
with the same group key and `cancel-in-progress: true`. GitHub concurrency is
repository-wide, so each invalidation job cancels the corresponding stale
self-hosted build/regression job as soon as a new commit is pushed.

The existing regression runner trap remains responsible for targeted container
and candidate-image removal. The image builder continues to remove its temporary
context. Partial BuildKit cache is not globally pruned because the runner is
shared and cache ownership cannot be safely inferred.

The finalize job still runs for failures and cancellations. If the selected GPU
job or validation job was cancelled, it skips the CPU-check polling loop and
completes the old SHA's aggregate check immediately with a non-success
conclusion. Normal successful runs continue to wait for the newest CPU checks.

### Claude review trust boundary

Claude review will stop loading the checked-out PR's project settings by using
only the isolated runner-home settings source. The trusted base-branch review
skill restoration and the existing read-only tool restrictions remain. This
blocks `.claude/settings.json` command hooks supplied by a PR without changing
the review trigger or comment flow.

### Release workflow

The Docker job checks the repository out into `LoongForge/`, builds with the
workspace root as context, and selects `LoongForge/docker/Dockerfile`. This
matches the Dockerfile's existing `COPY ./LoongForge` contract without changing
candidate builds or developer documentation.

Release concurrency is scoped by tag to prevent duplicate publication of the
same tag without causing distinct releases to replace each other's pending
runs. Docker Hub receives only the immutable package version tag. Automatic
publication of `latest` is removed; latest-version promotion can be designed as
a separate operator-controlled workflow later.

## Error Handling

- A malformed title produces one actionable validation error and a nonzero job
  result.
- A missing, incomplete, or non-success newest CPU check keeps polling until the
  existing timeout, then fails the aggregate check.
- A cancelled stale GPU job completes its old check promptly instead of polling
  CPU state for up to an hour.
- The invalidation workflow has no repository write permissions and checks out
  no PR code; its only effect is concurrency cancellation.
- Release build failures remain isolated to the Docker release job; package
  publication behavior is unchanged.

## Testing

Node unit tests will cover:

- valid single- and multi-module PR titles;
- empty and duplicate module rejection;
- invalid type/module rejection remains intact;
- newest success selection;
- newer failure or in-progress results overriding an older success;
- matching reusable-workflow names such as `pr-title / check`.

Workflow validation will run the Node tests alongside actionlint and YAML
parsing. Existing Python `ci_command` tests, shell syntax checks, Python
compilation, and `git diff --check` remain part of final verification.

## Expected Operational Impact

- Ordinary PR CPU runs retain the same required check name and dependencies.
- Manual dispatch remains available but no longer acts as a PR merge signal.
- A new PR commit now releases an occupied GPU runner instead of allowing stale
  regression to finish.
- Cancellation cleanup remains best-effort under GitHub's signal timeout;
  targeted containers and complete candidate images are removed when traps run,
  while partial shared BuildKit cache may remain.
- Release consumers must use immutable version tags because `latest` is no
  longer published by this workflow.
