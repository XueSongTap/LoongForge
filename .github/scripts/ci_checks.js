// Copyright 2026 The LoongForge Authors.
// SPDX-License-Identifier: Apache-2.0

'use strict';

function matchesCheckName(check, expectedName) {
  return check.name === expectedName || check.name.endsWith(` / ${expectedName}`);
}

function checkOrder(check) {
  const timestamp = Date.parse(check.started_at || check.created_at || '');
  return {
    timestamp: Number.isNaN(timestamp) ? 0 : timestamp,
    id: Number(check.id) || 0,
  };
}

function isNewer(candidate, current) {
  const candidateOrder = checkOrder(candidate);
  const currentOrder = checkOrder(current);
  return candidateOrder.timestamp > currentOrder.timestamp
    || (candidateOrder.timestamp === currentOrder.timestamp
      && candidateOrder.id > currentOrder.id);
}

function selectLatestChecks(checkRuns, expectedNames) {
  const selected = new Map();
  for (const expectedName of expectedNames) {
    for (const check of checkRuns) {
      if (!matchesCheckName(check, expectedName)) continue;
      const current = selected.get(expectedName);
      if (!current || isNewer(check, current)) {
        selected.set(expectedName, check);
      }
    }
  }
  return selected;
}

function shouldPollCpuChecks(results, suite) {
  return results.validate === 'success' && results[suite] === 'success';
}

module.exports = { matchesCheckName, selectLatestChecks, shouldPollCpuChecks };
