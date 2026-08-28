# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

# Sourced (not executed) by CI scripts. Loads the runner-provided image
# config when CI_CONFIG_PATH_IMAGE (or CI_CONFIG_PATH) is set, exporting
# every variable it defines.

config="${CI_CONFIG_PATH_IMAGE:-${CI_CONFIG_PATH:-}}"
[[ -z "$config" ]] && return 0
[[ -f "$config" ]] || { printf '%s\n' 'config: missing' >&2; exit 2; }
set -a
# shellcheck disable=SC1090
source "$config"
set +a
