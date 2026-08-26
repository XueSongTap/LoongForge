// Copyright 2026 The LoongForge Authors.
// SPDX-License-Identifier: Apache-2.0

'use strict';

const TYPES = ['feat', 'fix', 'refactor', 'perf', 'docs', 'test', 'chore', 'ci'];
const MODULES = new Set([
  'llm', 'vlm', 'vla', 'diffusion',
  'train', 'data', 'ops', 'ckpt', 'peft',
  'docker', 'xpu', 'ci', 'docs', 'tests', 'scripts', 'release',
]);

function validatePullRequestTitle(title) {
  const pattern = /^(?<breaking>\[BREAKING\])?\[(?<mods>[a-zA-Z0-9,\s\-]+)\]\s+(?<type>[a-zA-Z]+):\s+.+$/;
  const match = title.match(pattern);

  if (!match) {
    return {
      ok: false,
      message: [
        `PR title "${title}" does not match required format.`,
        '',
        'Expected: [<modules>] <type>: <description>',
        '      or: [BREAKING][<modules>] <type>: <description>',
        '',
        `Valid types:   ${TYPES.join(', ')}`,
        `Valid modules: ${[...MODULES].join(', ')}`,
        '',
        'Example: [llm, ckpt] feat: support Qwen3-Next checkpoint conversion',
      ].join('\n'),
    };
  }

  const type = match.groups.type.toLowerCase();
  if (!TYPES.includes(type)) {
    return {
      ok: false,
      message: `Invalid type "${type}". Valid types: ${TYPES.join(', ')}`,
    };
  }

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

  const invalidModules = modules.filter((moduleName) => !MODULES.has(moduleName));
  if (invalidModules.length > 0) {
    return {
      ok: false,
      message: [
        `Invalid modules: ${invalidModules.join(', ')}`,
        `Valid modules: ${[...MODULES].join(', ')}`,
      ].join('\n'),
    };
  }

  return { ok: true, message: 'PR title is valid.', type, modules };
}

module.exports = { validatePullRequestTitle };
