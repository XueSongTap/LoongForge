#!/usr/bin/env bash
# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

nvidia_smi_bin="${NVIDIA_SMI_BIN:-nvidia-smi}"
if ! command -v "$nvidia_smi_bin" >/dev/null 2>&1; then
  printf '%s\n' 'runner-gpu: unavailable' >&2
  exit 1
fi

if ! compute_caps="$($nvidia_smi_bin --query-gpu=compute_cap --format=csv,noheader,nounits 2>/dev/null)" ||
   [[ -z "${compute_caps//$'\n'/}" ]]; then
  printf '%s\n' 'runner-gpu: unavailable' >&2
  exit 1
fi

detected_target=""
while IFS= read -r raw_cap; do
  cap="$(printf '%s' "$raw_cap" | tr -d '[:space:]')"
  case "$cap" in
    8.*)
      current_target=a
      ;;
    10.*|11.*|12.*)
      current_target=p
      ;;
    *)
      printf '%s\n' 'runner-gpu: unsupported' >&2
      exit 1
      ;;
  esac

  if [[ -z "$detected_target" ]]; then
    detected_target="$current_target"
  elif [[ "$detected_target" != "$current_target" ]]; then
    printf '%s\n' 'runner-gpu: mixed targets' >&2
    exit 1
  fi
done <<< "$compute_caps"

[[ -n "$detected_target" ]] || {
  printf '%s\n' 'runner-gpu: unavailable' >&2
  exit 1
}

printf '%s\n' "$detected_target"
