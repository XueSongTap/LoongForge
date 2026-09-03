// Copyright 2026 The LoongForge Authors.
// SPDX-License-Identifier: Apache-2.0

const GPU_CHECK_NAME = 'gpu-regression';
const ACTIONS_BOT = 'github-actions[bot]';

function hasGpuValidation(checkRuns, comments) {
  if (checkRuns.some((run) => run?.name === GPU_CHECK_NAME)) {
    return true;
  }
  return comments.some((comment) =>
    comment?.user?.login === ACTIONS_BOT &&
    typeof comment.body === 'string' &&
    comment.body.includes('<!-- loongforge-gpu-regression:'),
  );
}

function findActionRequiredCheck(checkRuns, headSha) {
  return checkRuns
    .filter((run) =>
      run?.name === GPU_CHECK_NAME &&
      run?.head_sha === headSha &&
      run?.status === 'completed' &&
      run?.conclusion === 'action_required',
    )
    .sort((left, right) => (right.id || 0) - (left.id || 0))[0] || null;
}

function gpuConclusion(results, suite) {
  const requiredJobs = ['validate', suite];
  const failed = requiredJobs.filter((name) => results[name] !== 'success');
  const suiteResult = results[suite];
  const conclusion = failed.length
    ? (suiteResult === 'cancelled' ? 'cancelled' : 'failure')
    : 'success';
  return { conclusion, failed };
}

module.exports = {
  ACTIONS_BOT,
  GPU_CHECK_NAME,
  findActionRequiredCheck,
  gpuConclusion,
  hasGpuValidation,
};
