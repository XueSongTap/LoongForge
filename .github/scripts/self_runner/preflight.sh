#!/usr/bin/env bash
# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

suite="${1:-}"
build_image="${2:-false}"
[[ "$suite" =~ ^(llm_vlm|embodied)$ ]] || { printf '%s\n' 'suite: invalid' >&2; exit 2; }
[[ "$build_image" == true || "$build_image" == false ]] || {
  printf '%s\n' 'build_image: invalid' >&2
  exit 2
}

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "$script_dir/../load_ci_config.sh"

required=(
  LOONGFORGE_DEFAULT_IMAGE
  LOONGFORGE_HOST_DATA_ROOT
  LOONGFORGE_CONTAINER_DATA_ROOT
  LOONGFORGE_HOST_OUTPUT_ROOT
  LOONGFORGE_CONTAINER_OUTPUT_ROOT
  LOONGFORGE_CONTAINER_SOURCE
  LOONGFORGE_RUNNER_LOG_ROOT
  TRITON_LIBCUDA_PATH
  LOONGFORGE_GPU_DEVICE
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf '%s\n' "$name" >&2
    exit 2
  fi
done

for name in LOONGFORGE_HOST_DATA_ROOT LOONGFORGE_HOST_OUTPUT_ROOT LOONGFORGE_RUNNER_LOG_ROOT TRITON_LIBCUDA_PATH; do
  if [[ ! -e "${!name}" ]]; then
    printf '%s\n' 'mounts: missing' >&2
    exit 2
  fi
done

docker_bin="${DOCKER_BIN:-docker}"
if ! "$docker_bin" version >/dev/null 2>&1; then
  printf '%s\n' 'docker: missing' >&2
  exit 1
fi
printf '%s\n' 'docker: ok'

if [[ "$build_image" == true ]]; then
  if [[ "${LOONGFORGE_ALLOW_PR_IMAGE_BUILD:-false}" != true ]]; then
    printf '%s\n' 'build_image: disabled' >&2
    exit 2
  fi
  if ! "$docker_bin" buildx version >/dev/null 2>&1; then
    printf '%s\n' 'buildx: missing' >&2
    exit 1
  fi
  printf '%s\n' 'buildx: ok'
fi

if ! "$docker_bin" run --rm --device="$LOONGFORGE_GPU_DEVICE" "$LOONGFORGE_DEFAULT_IMAGE" true >/dev/null 2>&1; then
  printf '%s\n' 'image-device: invalid' >&2
  exit 1
fi
printf '%s\n' 'image-device: ok'
printf '%s\n' 'mounts: ok'
