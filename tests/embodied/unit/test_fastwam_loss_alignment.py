# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the FastWAM loss-alignment options.

Covers the FastWAM-style action/proprio normalization
(``data.norm_stats_path``), the ``--step-seeded-noise`` RNG context and the
FastWAM action scheduler default.
"""

import json
from types import SimpleNamespace

import pytest
import torch

from loongforge.embodied.data.datasets.fastwam.transforms.fastwam_transform import (
    FastWAMLinearNormalizeTransform,
    _fastwam_linear_params,
)
from loongforge.embodied.model.fastwam.modeling_configuration_fastwam import FastWAMModelConfig
from loongforge.embodied.train.trainers.supervised.finetune_trainer import FinetuneTrainer


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


def _fake_trainer(enabled, seed=7, rank=0, step=0):
    return SimpleNamespace(
        training_args=SimpleNamespace(step_seeded_noise=enabled, seed=seed),
        ctx=SimpleNamespace(rank=rank),
        completed_steps=step,
    )


def _draw(trainer):
    with FinetuneTrainer._noise_rng_context(trainer):
        return torch.randn(4)


def test_step_seeded_noise_depends_only_on_seed_rank_step():
    torch.manual_seed(0)
    a = _draw(_fake_trainer(True, step=3))
    torch.randn(100)  # consume RNG in between, e.g. data loading
    b = _draw(_fake_trainer(True, step=3))
    assert torch.equal(a, b)
    assert not torch.equal(a, _draw(_fake_trainer(True, step=4)))
    assert not torch.equal(a, _draw(_fake_trainer(True, rank=1, step=3)))


def test_step_seeded_noise_leaves_outer_rng_untouched():
    torch.manual_seed(0)
    _draw(_fake_trainer(True, step=3))
    after = torch.randn(4)
    torch.manual_seed(0)
    assert torch.equal(after, torch.randn(4))


def test_step_seeded_noise_disabled_uses_global_rng():
    torch.manual_seed(0)
    a = _draw(_fake_trainer(False))
    torch.manual_seed(0)
    assert torch.equal(a, torch.randn(4))


def test_action_scheduler_defaults_match_fastwam():
    cfg = FastWAMModelConfig.__dataclass_fields__
    action = cfg["action_scheduler"].default_factory()
    video = cfg["video_scheduler"].default_factory()
    assert action["train_shift"] == 1.0 and action["infer_shift"] == 1.0
    assert video["train_shift"] == 5.0 and video["infer_shift"] == 5.0
