# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for FastWAM parity with the official implementation.

Covers the FastWAM-style action/proprio normalization
(``data.norm_stats_path``) and the FastWAM action scheduler default.
"""

import json

import pytest
import torch

from loongforge.embodied.data.datasets.fastwam.transforms.fastwam_transform import (
    FastWAMLinearNormalizeTransform,
    _fastwam_linear_params,
)
from loongforge.embodied.model.fastwam.modeling_configuration_fastwam import FastWAMModelConfig


def _stats(lo, hi, extra=None):
    out = {"global_min": lo, "global_max": hi, "global_mean": [0.0] * len(lo), "global_std": [1.0] * len(lo)}
    out.update(extra or {})
    return out


def test_minmax_params_map_range_to_unit_interval_and_skip_constant_dims():
    scale, offset = _fastwam_linear_params(_stats([0.0, -2.0, 3.0], [4.0, 2.0, 3.0]), "min/max")
    x = torch.tensor([[0.0, -2.0, 3.0], [4.0, 2.0, 3.0]])
    y = x * scale + offset
    assert torch.allclose(y[:, :2], torch.tensor([[-1.0, -1.0], [1.0, 1.0]]))
    # Constant dim (range < 1e-4): scale 1, offset -min -> value shifted to 0.
    assert scale[2] == 1.0 and y[0, 2] == 0.0


def test_unknown_norm_mode_raises():
    with pytest.raises(ValueError):
        _fastwam_linear_params(_stats([0.0], [1.0]), "q99")


@pytest.fixture
def stats_file(tmp_path):
    stats = {
        "action": {"default": _stats([0.0, 0.0], [2.0, 2.0])},
        "state": {"default": _stats([-1.0], [1.0])},
    }
    path = tmp_path / "dataset_stats.json"
    path.write_text(json.dumps(stats))
    return str(path)


def test_normalize_zeroes_padded_delta_dims_and_clamps(stats_file):
    transform = FastWAMLinearNormalizeTransform(stats_file, delta_action_dim_mask=[True, False])
    data = {
        "action": torch.tensor([[2.0, 2.0], [2.0, 2.0], [100.0, 0.0]]),
        "action_is_pad": torch.tensor([False, True, False]),
        "observation.state": torch.tensor([[0.5]]),
    }
    out = transform.apply(data)
    # Padded step: delta dim 0 is zeroed before normalization (0 -> -1); dim 1 is kept.
    expected = torch.tensor([[1.0, 1.0], [-1.0, 1.0], [5.0, -1.0]])
    assert torch.allclose(out["action"], expected)
    assert torch.allclose(out["observation.state"], torch.tensor([[0.5]]))


def test_normalize_unapply_roundtrip(stats_file):
    transform = FastWAMLinearNormalizeTransform(stats_file)
    action = torch.tensor([[0.5, 1.5]])
    out = transform.unapply(transform.apply({"action": action.clone()}))
    assert torch.allclose(out["action"], action)


def test_action_scheduler_defaults_match_fastwam():
    cfg = FastWAMModelConfig.__dataclass_fields__
    action = cfg["action_scheduler"].default_factory()
    video = cfg["video_scheduler"].default_factory()
    assert action["train_shift"] == 1.0 and action["infer_shift"] == 1.0
    assert video["train_shift"] == 5.0 and video["infer_shift"] == 5.0
