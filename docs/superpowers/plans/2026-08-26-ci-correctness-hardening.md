# CI Correctness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix confirmed CI correctness, cancellation, release-context, and Claude hook-loading defects without changing the required PR gate shape, GPU suite topology, or runner-local secret flow.

**Architecture:** Pure title validation and check-run selection move into small CommonJS helpers exercised by Node's built-in test runner. Workflow-only contracts are guarded by static Node tests, while stale GPU execution is cancelled through repository-wide job concurrency shared with a trusted `pull_request_target` invalidation workflow.

**Tech Stack:** GitHub Actions YAML, `actions/github-script`, CommonJS JavaScript, Node `node:test`, Bash, Docker BuildKit.

## Global Constraints

- Keep the seven CPU checks and required PR check name `ci-gate` unchanged.
- Keep separate `llm_vlm` and `embodied` GPU jobs and their existing runner mappings.
- Do not enable the temporarily unavailable `llm_vlm` suite.
- Do not change runner-local BuildKit secret handling.
- Do not force source-manifest use in release builds.
- Do not globally prune shared BuildKit caches.
- Publish Docker Hub version tags only; do not publish `latest`.
- Every behavior change follows a visible RED → GREEN test cycle.

---

## File Map

- Create `.github/scripts/pr_title.js`: pure PR-title parser and validator.
- Create `.github/scripts/ci_checks.js`: reusable check-name matching, newest-run selection, and cancellation polling decision.
- Create `.github/workflows/gpu-invalidate.yml`: trusted synchronize-event jobs that cancel stale suite runner jobs by concurrency key.
- Create `tests/test_ci_helpers.js`: Node unit and workflow-contract tests.
- Modify `.github/workflows/pr-title.yml`: checkout and call the tested title helper.
- Modify `.github/workflows/ci-gate.yml`: use a distinct manual final-check name.
- Modify `.github/workflows/gpu-regression.yml`: job-level concurrency, newest CPU checks, and cancellation fast path.
- Modify `.github/workflows/claude-review.yml`: exclude project settings.
- Modify `.github/workflows/release.yml`: correct context, immutable image tag, and tag concurrency.
- Modify `.github/workflows/workflow-lint.yml`: execute Node CI helper tests.
- Modify `.github/workflows/README.md`, `.github/CI_SETUP.md`, and `CONTRIBUTING.md`: document manual-gate, cancellation, and immutable-release behavior.

---

### Task 1: Extract and test PR-title validation

**Files:**
- Create: `.github/scripts/pr_title.js`
- Create: `tests/test_ci_helpers.js`
- Modify: `.github/workflows/pr-title.yml:13-63`

**Interfaces:**
- Produces: `validatePullRequestTitle(title: string): { ok: boolean, message: string, type?: string, modules?: string[] }`
- Consumes: PR title from `context.payload.pull_request.title`.

- [ ] **Step 1: Write failing title tests**

Create `tests/test_ci_helpers.js` with Node's built-in test API and cases for a legal title, an empty module list, duplicate modules, and invalid modules:

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const { validatePullRequestTitle } = require('../.github/scripts/pr_title');

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
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `node --test --test-name-pattern='title|module' tests/test_ci_helpers.js`

Expected: FAIL with `Cannot find module '../.github/scripts/pr_title'`.

- [ ] **Step 3: Implement the minimal title helper**

Create `.github/scripts/pr_title.js` with the existing type/module lists, the existing optional `[BREAKING]` format, normalization, and explicit empty/duplicate validation. Return error strings suitable for `core.setFailed`, and export `validatePullRequestTitle` with `module.exports`.

Core validation order:

```javascript
const modules = match.groups.mods
  .split(',')
  .map((value) => value.trim().toLowerCase())
  .filter(Boolean);

if (modules.length === 0) {
  return { ok: false, message: 'At least one valid module is required.' };
}
if (new Set(modules).size !== modules.length) {
  return { ok: false, message: 'Duplicate modules are not allowed.' };
}
```

- [ ] **Step 4: Make the workflow call the tested helper**

Add a credential-free checkout before `actions/github-script`, then replace the inline parser with:

```javascript
const { validatePullRequestTitle } = require('./.github/scripts/pr_title');
const result = validatePullRequestTitle(context.payload.pull_request?.title || '');
if (!result.ok) {
  core.setFailed(result.message);
  return;
}
core.info(`OK: type=${result.type}, modules=[${result.modules.join(', ')}]`);
```

- [ ] **Step 5: Verify GREEN**

Run: `node --test --test-name-pattern='title|module' tests/test_ci_helpers.js`

Expected: 4 passing tests, 0 failures.

- [ ] **Step 6: Commit the title fix**

```bash
git add .github/scripts/pr_title.js .github/workflows/pr-title.yml tests/test_ci_helpers.js
git commit -m "ci: harden pull request title validation"
```

---

### Task 2: Select only newest CPU check runs

**Files:**
- Create: `.github/scripts/ci_checks.js`
- Modify: `tests/test_ci_helpers.js`
- Modify: `.github/workflows/gpu-regression.yml:247-277`

**Interfaces:**
- Produces: `selectLatestChecks(checkRuns: object[], expectedNames: string[]): Map<string, object>`
- Produces: `shouldPollCpuChecks(results: Record<string, string>, suite: string): boolean`
- Consumes: GitHub Checks API `check_runs` objects and `ci/cpu-checks.json` names.

- [ ] **Step 1: Write failing newest-run tests**

Append tests that provide two `pr-title / check` runs for the same SHA: an older success and a newer failure or in-progress result. Also test that cancelled validation disables polling:

```javascript
const {
  selectLatestChecks,
  shouldPollCpuChecks,
} = require('../.github/scripts/ci_checks');

test('newer failed check overrides older success', () => {
  const selected = selectLatestChecks([
    { id: 1, name: 'pr-title / check', status: 'completed', conclusion: 'success', started_at: '2026-08-26T01:00:00Z' },
    { id: 2, name: 'pr-title / check', status: 'completed', conclusion: 'failure', started_at: '2026-08-26T02:00:00Z' },
  ], ['check']);
  assert.equal(selected.get('check').conclusion, 'failure');
});

test('newer in-progress check prevents terminal success', () => {
  const selected = selectLatestChecks([
    { id: 1, name: 'lint / ruff', status: 'completed', conclusion: 'success', started_at: '2026-08-26T01:00:00Z' },
    { id: 2, name: 'lint / ruff', status: 'in_progress', conclusion: null, started_at: '2026-08-26T02:00:00Z' },
  ], ['ruff']);
  assert.equal(selected.get('ruff').status, 'in_progress');
});

test('cancelled GPU validation skips CPU polling', () => {
  assert.equal(shouldPollCpuChecks({ validate: 'cancelled', embodied: 'skipped' }, 'embodied'), false);
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `node --test --test-name-pattern='newer|polling' tests/test_ci_helpers.js`

Expected: FAIL with `Cannot find module '../.github/scripts/ci_checks'`.

- [ ] **Step 3: Implement selection and polling helpers**

Implement exact-or-suffix matching, sort by `started_at || created_at`, use numeric `id` as a deterministic tie-breaker, and keep the first run for each expected logical name. `shouldPollCpuChecks` returns false when validation or the selected suite result is `cancelled`.

```javascript
function matchesCheckName(check, expectedName) {
  return check.name === expectedName || check.name.endsWith(` / ${expectedName}`);
}
```

- [ ] **Step 4: Use the helper in both polling and final evaluation**

Require the helper in the finalize GitHub Script. On every API response, call `selectLatestChecks`; declare terminal only when every selected newest run is completed. Build `missingCpu` from the same selected map. If `shouldPollCpuChecks` is false, skip the API polling loop and complete the custom check with conclusion `cancelled`.

- [ ] **Step 5: Verify GREEN**

Run: `node --test --test-name-pattern='newer|polling' tests/test_ci_helpers.js`

Expected: 3 passing tests, 0 failures.

- [ ] **Step 6: Commit the aggregation fix**

```bash
git add .github/scripts/ci_checks.js .github/workflows/gpu-regression.yml tests/test_ci_helpers.js
git commit -m "ci: aggregate the newest CPU check runs"
```

---

### Task 3: Cancel stale GPU jobs on new commits

**Files:**
- Create: `.github/workflows/gpu-invalidate.yml`
- Modify: `.github/workflows/gpu-regression.yml:39-41,109-221`
- Modify: `tests/test_ci_helpers.js`

**Interfaces:**
- Consumes/produces shared concurrency keys `gpu-regression-<PR>-llm_vlm` and `gpu-regression-<PR>-embodied`.
- Produces no repository mutations or artifacts.

- [ ] **Step 1: Write failing workflow-contract tests**

Read the workflow files as text and assert that regression runner jobs and invalidation jobs contain identical SHA-free keys, while the old workflow-level SHA key is absent:

```javascript
const fs = require('node:fs');
const path = require('node:path');
const repoRoot = path.resolve(__dirname, '..');

function readWorkflow(name) {
  return fs.readFileSync(path.join(repoRoot, '.github/workflows', name), 'utf8');
}

test('new commits invalidate suite GPU jobs without SHA-scoped concurrency', () => {
  const regression = readWorkflow('gpu-regression.yml');
  const invalidation = readWorkflow('gpu-invalidate.yml');
  assert.doesNotMatch(regression, /group: gpu-regression-.*head_sha/);
  for (const suite of ['llm_vlm', 'embodied']) {
    assert.match(regression, new RegExp(`group: gpu-regression-.*-${suite}`));
    assert.match(invalidation, new RegExp(`group: gpu-regression-.*-${suite}`));
  }
});
```

- [ ] **Step 2: Run the test and verify RED**

Run: `node --test --test-name-pattern='invalidate suite GPU' tests/test_ci_helpers.js`

Expected: FAIL because `.github/workflows/gpu-invalidate.yml` does not exist.

- [ ] **Step 3: Move concurrency onto suite runner jobs**

Delete workflow-level concurrency. Add these job-level blocks to `llm_vlm` and `embodied` respectively:

```yaml
concurrency:
  group: gpu-regression-${{ inputs.pr_number }}-llm_vlm
  cancel-in-progress: true
```

```yaml
concurrency:
  group: gpu-regression-${{ inputs.pr_number }}-embodied
  cancel-in-progress: true
```

- [ ] **Step 4: Add the trusted invalidation workflow**

Create a `pull_request_target` workflow for `synchronize` with `permissions: {}` and two Ubuntu jobs. Each job uses the matching suite concurrency key with `cancel-in-progress: true`, checks out no code, and runs only an explanatory `echo` step.

- [ ] **Step 5: Verify GREEN**

Run: `node --test --test-name-pattern='invalidate suite GPU' tests/test_ci_helpers.js`

Expected: 1 passing test, 0 failures.

- [ ] **Step 6: Commit stale-run cancellation**

```bash
git add .github/workflows/gpu-invalidate.yml .github/workflows/gpu-regression.yml tests/test_ci_helpers.js
git commit -m "ci: cancel stale GPU jobs on PR updates"
```

---

### Task 4: Harden manual, Claude, and release workflow contracts

**Files:**
- Modify: `.github/workflows/ci-gate.yml:38-40`
- Modify: `.github/workflows/claude-review.yml:220-231`
- Modify: `.github/workflows/release.yml:1-69`
- Modify: `tests/test_ci_helpers.js`

**Interfaces:**
- PR final job name remains `ci-gate`; dispatch final job name becomes `manual-ci-gate`.
- Claude settings source is `user`, whose HOME is the isolated runner temp directory.
- Docker release input layout is workspace `LoongForge/docker/Dockerfile` with context `.`.

- [ ] **Step 1: Write failing workflow-contract tests**

Add tests asserting:

```javascript
test('manual dispatch cannot publish the required PR gate name', () => {
  const workflow = readWorkflow('ci-gate.yml');
  assert.match(workflow, /github\.event_name == 'pull_request'.*'ci-gate'.*'manual-ci-gate'/);
});

test('Claude review excludes project settings', () => {
  const workflow = readWorkflow('claude-review.yml');
  assert.match(workflow, /--setting-sources user/);
  assert.doesNotMatch(workflow, /--setting-sources project/);
});

test('release uses matching context and immutable image tags', () => {
  const workflow = readWorkflow('release.yml');
  assert.match(workflow, /path: LoongForge/);
  assert.match(workflow, /file: LoongForge\/docker\/Dockerfile/);
  assert.doesNotMatch(workflow, /DOCKERHUB_IMAGE.*:latest/);
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `node --test --test-name-pattern='manual dispatch|Claude review|release uses' tests/test_ci_helpers.js`

Expected: 3 failures describing the current workflow contracts.

- [ ] **Step 3: Implement the manual gate name**

Set the final job display name to:

```yaml
name: ${{ github.event_name == 'pull_request' && 'ci-gate' || 'manual-ci-gate' }}
```

- [ ] **Step 4: Exclude project settings from Claude review**

Replace `--setting-sources project` with `--setting-sources user`. Keep the isolated `HOME`, trusted skill restoration, strict MCP config, allowed tools, and disallowed tools unchanged.

- [ ] **Step 5: Correct the release layout and tags**

Add tag-scoped concurrency, checkout the Docker job with `path: LoongForge`, set `file: LoongForge/docker/Dockerfile`, retain `context: .`, and remove the Docker Hub `latest` tag. Leave PyPI publication unchanged.

- [ ] **Step 6: Verify GREEN**

Run: `node --test --test-name-pattern='manual dispatch|Claude review|release uses' tests/test_ci_helpers.js`

Expected: 3 passing tests, 0 failures.

- [ ] **Step 7: Commit the workflow hardening**

```bash
git add .github/workflows/ci-gate.yml .github/workflows/claude-review.yml .github/workflows/release.yml tests/test_ci_helpers.js
git commit -m "ci: harden manual review and release workflows"
```

---

### Task 5: Run helper tests in CI and update operator documentation

**Files:**
- Modify: `.github/workflows/workflow-lint.yml:20-34`
- Modify: `.github/workflows/README.md`
- Modify: `.github/CI_SETUP.md`
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Workflow lint invokes `node --test tests/test_ci_helpers.js` using the runner's Node runtime.
- Documentation describes behavior already implemented by Tasks 1-4.

- [ ] **Step 1: Add the Node regression suite to workflow lint**

Add this step after actionlint and YAML validation:

```yaml
- name: Run CI helper tests
  run: node --test tests/test_ci_helpers.js
```

- [ ] **Step 2: Update workflow documentation**

Document that manual dispatch skips PR-only checks and publishes
`manual-ci-gate`; new commits cancel stale suite GPU jobs; cancellation cleanup
is targeted and best-effort; releases publish only immutable version tags.

- [ ] **Step 3: Run all focused tests**

Run:

```bash
node --test tests/test_ci_helpers.js
python -m pytest -q tests/test_ci_command.py
```

Expected: all Node tests pass and `7 passed` for Python.

- [ ] **Step 4: Commit tests and docs**

```bash
git add .github/workflows/workflow-lint.yml .github/workflows/README.md .github/CI_SETUP.md CONTRIBUTING.md
git commit -m "docs: document hardened CI behavior"
```

---

### Task 6: Full verification

**Files:**
- Verify all files changed since design commit `2e2a844`.

**Interfaces:**
- Consumes the complete implementation from Tasks 1-5.
- Produces verification evidence; no new behavior.

- [ ] **Step 1: Run unit tests**

```bash
node --test tests/test_ci_helpers.js
python -m pytest -q tests/test_ci_command.py
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Run workflow and YAML validation**

Run repository actionlint if installed. If it is unavailable locally, install exactly `github.com/rhysd/actionlint/cmd/actionlint@v1.7.7` into a temporary `GOBIN` and run it. Parse every `.github/workflows/*.yml` with `yaml.safe_load` using PyYAML 6.0.2.

Expected: actionlint exits 0; every workflow prints successfully from the YAML parser.

- [ ] **Step 3: Run shell and repository hygiene checks**

```bash
git diff --check 2e2a844...HEAD
bash -n .github/scripts/*.sh .github/scripts/self_runner/*.sh docker/*.sh
python -m compileall -q .github/scripts tests/test_ci_command.py
git status --short
```

Expected: all validation commands exit 0; status contains only intentional implementation changes, or is clean after task commits.

- [ ] **Step 4: Inspect the final diff against the design**

Run: `git diff --stat 2e2a844...HEAD && git diff 2e2a844...HEAD -- .github tests CONTRIBUTING.md`

Confirm every design goal has a corresponding change and every non-goal remains untouched, especially candidate BuildKit secret arguments and the two separate GPU suite jobs.
