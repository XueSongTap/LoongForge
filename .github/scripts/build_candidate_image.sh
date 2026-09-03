#!/usr/bin/env bash
# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

target="${1:-auto}"
case "$target" in
  a|p|auto) ;;
  *) echo "unsupported image target" >&2; exit 2 ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${script_dir}/load_ci_config.sh"

if [[ "$target" == auto ]]; then
  detected_target="$($script_dir/self_runner/detect_gpu_target.sh)" || exit 1
  target="$detected_target"
fi

builder="${LOONGFORGE_IMAGE_BUILDER:-$script_dir/self_runner/build_candidate_image.sh}"
[[ -x "$builder" ]] || { echo "LOONGFORGE_IMAGE_BUILDER must point to an executable" >&2; exit 2; }
revision="$("$builder" \
  --target "$target" \
  --sha "${HEAD_SHA:?HEAD_SHA is required}" \
  --source "${SOURCE_DIR:?SOURCE_DIR is required}" \
  --pr "${PR_NUMBER:?PR_NUMBER is required}" \
  --tree-sha "${TREE_SHA:?TREE_SHA is required}")"
[[ "$revision" =~ ^[A-Za-z0-9._:/-]+$ ]] || { echo "image builder returned an invalid revision" >&2; exit 2; }
echo "revision=$revision" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
