#!/usr/bin/env bash
# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

min_free_gb="${1-}"
[[ -n "$min_free_gb" ]] || exit 0
[[ "$min_free_gb" =~ ^[0-9]{1,6}$ ]] || {
  printf '%s\n' 'docker-storage: invalid configuration' >&2
  exit 2
}

docker_bin="${DOCKER_BIN:-docker}"
if ! docker_root=$("$docker_bin" info --format '{{.DockerRootDir}}' 2>/dev/null) || \
    [[ -z "$docker_root" || ! -d "$docker_root" ]]; then
  printf '%s\n' 'docker-storage: unavailable' >&2
  exit 1
fi
if ! free_kb=$(df -Pk "$docker_root" 2>/dev/null | awk 'NR == 2 { print $4 }') || \
    [[ ! "$free_kb" =~ ^[0-9]+$ ]]; then
  printf '%s\n' 'docker-storage: unavailable' >&2
  exit 1
fi

required_kb=$((min_free_gb * 1024 * 1024))
if (( free_kb < required_kb )); then
  printf '%s\n' 'docker-storage: insufficient' >&2
  exit 1
fi
printf '%s\n' 'docker-storage: ok'
