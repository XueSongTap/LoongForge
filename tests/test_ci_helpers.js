// Copyright 2026 The LoongForge Authors.
// SPDX-License-Identifier: Apache-2.0

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { validatePullRequestTitle } = require('../.github/scripts/pr_title');
const {
  selectLatestChecks,
  shouldPollCpuChecks,
} = require('../.github/scripts/ci_checks');

const repoRoot = path.resolve(__dirname, '..');

function readWorkflow(name) {
  return fs.readFileSync(path.join(repoRoot, '.github/workflows', name), 'utf8');
}

test('accepts a valid multi-module title', () => {
  const result = validatePullRequestTitle('[llm, ckpt] feat: add converter');
  assert.equal(result.ok, true);
  assert.deepEqual(result.modules, ['llm', 'ckpt']);
});

test('rejects a title without a module', () => {
  const result = validatePullRequestTitle('[, ] feat: empty modules');
  assert.equal(result.ok, false);
  assert.match(result.message, /at least one valid module/i);
});

test('rejects duplicate modules', () => {
  const result = validatePullRequestTitle('[ci, ci] fix: duplicate module');
  assert.equal(result.ok, false);
  assert.match(result.message, /duplicate module/i);
});

test('rejects an unknown module', () => {
  const result = validatePullRequestTitle('[unknown] fix: unknown module');
  assert.equal(result.ok, false);
  assert.match(result.message, /invalid modules/i);
});

test('newer failed check overrides older success', () => {
  const selected = selectLatestChecks([
    {
      id: 1,
      name: 'pr-title / check',
      status: 'completed',
      conclusion: 'success',
      started_at: '2026-08-26T01:00:00Z',
    },
    {
      id: 2,
      name: 'pr-title / check',
      status: 'completed',
      conclusion: 'failure',
      started_at: '2026-08-26T02:00:00Z',
    },
  ], ['check']);
  assert.equal(selected.get('check').conclusion, 'failure');
});

test('newer in-progress check prevents terminal success', () => {
  const selected = selectLatestChecks([
    {
      id: 1,
      name: 'lint / ruff',
      status: 'completed',
      conclusion: 'success',
      started_at: '2026-08-26T01:00:00Z',
    },
    {
      id: 2,
      name: 'lint / ruff',
      status: 'in_progress',
      conclusion: null,
      started_at: '2026-08-26T02:00:00Z',
    },
  ], ['ruff']);
  assert.equal(selected.get('ruff').status, 'in_progress');
});

test('cancelled GPU validation skips CPU polling', () => {
  assert.equal(
    shouldPollCpuChecks({ validate: 'cancelled', embodied: 'skipped' }, 'embodied'),
    false,
  );
});

test('new commits invalidate suite GPU jobs without SHA-scoped concurrency', () => {
  const regression = readWorkflow('gpu-regression.yml');
  const invalidation = readWorkflow('gpu-invalidate.yml');
  assert.doesNotMatch(regression, /group: gpu-regression-.*head_sha/);
  for (const suite of ['llm_vlm', 'embodied']) {
    assert.match(regression, new RegExp(`group: gpu-regression-.*-${suite}`));
    assert.match(invalidation, new RegExp(`group: gpu-regression-.*-${suite}`));
  }
});

test('PR check exposes queued build regression and cancellation stages', () => {
  const dispatch = readWorkflow('ok-to-test.yml');
  const regression = readWorkflow('gpu-regression.yml');
  assert.match(dispatch, /title: 'GPU validation queued'/);
  assert.match(regression, /title: 'Building candidate image'/);
  assert.match(regression, /title: `Running \$\{process\.env\.SUITE\} regression`/);
  assert.match(regression, /GPU validation cancelled/);
});

test('manual dispatch cannot publish the required PR gate name', () => {
  const workflow = readWorkflow('ci-gate.yml');
  assert.match(
    workflow,
    /github\.event_name == 'pull_request'.*'ci-gate'.*'manual-ci-gate'/,
  );
});

test('Claude review excludes project settings', () => {
  const workflow = readWorkflow('claude-review.yml');
  assert.match(workflow, /--setting-sources user/);
  assert.doesNotMatch(workflow, /--setting-sources project/);
});

test('release uses matching context and immutable image tags', () => {
  const workflow = readWorkflow('release.yml');
  assert.match(workflow, /group: release-\$\{\{ github\.ref \}\}/);
  assert.match(workflow, /path: LoongForge/);
  assert.match(workflow, /file: LoongForge\/docker\/Dockerfile/);
  assert.doesNotMatch(workflow, /DOCKERHUB_IMAGE.*:latest/);
});
