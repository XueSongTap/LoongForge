# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

"""Correctness harness for fp8_a2a_allgather_hook.

Runs under torchrun. Checks the hook against native AllReduce on shapes that
exercise the layout arithmetic (non-divisible numel, ragged tail, single tile)
and reports gradient-domain error, which is the metric that matters -- loss is
known to be insensitive to a 15x growth in gradient quantization error.

    torchrun --nproc_per_node 8 test_fp8_a2a.py
"""

import os
import sys

import torch
import torch.distributed as dist

sys.path.insert(0, os.environ.get("LOONGFORGE_PATH", "."))

from loongforge.embodied.distributed.ddp_utils.fp8_a2a_comm import (  # noqa: E402
    configure,
    fp8_a2a_allgather_hook,
    reset_scratch,
)

# Force every case through the FP8 path. With the default min_mib the small
# shapes fall back to plain AllReduce and the layout/masking logic goes untested
# -- which looks like a pass (rel_l2 lands at ~1.4x bf16) rather than a skip.
configure(min_mib=0)


class FakeBucket:
    """Minimal stand-in for DDP's GradBucket (buffer() + index())."""

    def __init__(self, tensor, index=0):
        self._t = tensor
        self._i = index

    def buffer(self):
        return self._t

    def index(self):
        return self._i


def rel_l2(got, want):
    return (got - want).float().norm() / want.float().norm()


def cosine(got, want):
    g, w = got.float().flatten(), want.float().flatten()
    return torch.dot(g, w) / (g.norm() * w.norm())


def check(numel, rank, world_size, dtype=torch.bfloat16, index=0, scale=1.0):
    torch.manual_seed(1234 + rank)
    # Gradient-like: heavy-tailed, spans several orders of magnitude, so a
    # single global scale would underflow most of it.
    grad = (torch.randn(numel, device="cuda", dtype=torch.float32) * scale
            * torch.exp(torch.randn(numel, device="cuda") * 2.0)).to(dtype)

    reference = grad.clone().float()
    dist.all_reduce(reference)
    reference /= world_size

    got = grad.clone()
    fut = fp8_a2a_allgather_hook(None, FakeBucket(got, index))
    out = fut.wait()
    torch.cuda.synchronize()

    assert out.data_ptr() == got.data_ptr(), "hook must resolve to bucket.buffer()"

    err = rel_l2(out, reference).item()
    cos = cosine(out, reference).item()

    # bf16 AllReduce is itself lossy; quote it so the fp8 number has a scale.
    # For fp32 buckets the round-trip is exact, so there is no ratio to quote.
    bf16_err = rel_l2(reference.to(dtype), reference).item()
    ratio = f"{err / bf16_err:5.1f}x" if bf16_err > 0 else "  n/a"

    if rank == 0:
        print(f"  numel={numel:>11} {str(dtype).replace('torch.', ''):>8}  "
              f"rel_l2={err:.4e}  (dtype round-trip {bf16_err:.4e}, {ratio})  "
              f"cos={cos:.8f}")
    return err


def check_big(numel, rank, world_size, index):
    """Same check, memory-lean, for sizes where int32 byte offsets would wrap.

    Generates directly in bf16 and keeps only one fp32 copy alive, so a 2.2e9
    element case fits alongside the hook's own ~5 GiB of scratch.
    """
    torch.manual_seed(99 + rank)
    grad = torch.randn(numel, device="cuda", dtype=torch.bfloat16)

    reference = grad.float()
    dist.all_reduce(reference)
    reference /= world_size

    got = grad
    out = fp8_a2a_allgather_hook(None, FakeBucket(got, index)).wait()
    torch.cuda.synchronize()

    err = rel_l2(out, reference).item()
    # No cosine here: torch.dot itself caps at 2^31-1 elements.
    peak = torch.cuda.max_memory_allocated() / 2**30
    if rank == 0:
        print(f"  numel={numel:>11} bfloat16  rel_l2={err:.4e}  "
              f"peak={peak:.1f} GiB")
    assert err < 0.1, f"int64 offsets look wrong: rel_l2={err:.3e}"
    del reference, grad, out
    torch.cuda.empty_cache()
    return err


def main():
    dist.init_process_group("nccl")
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    torch.cuda.set_device(rank % torch.cuda.device_count())

    if rank == 0:
        print(f"world_size={world_size}, block=256, tile=2048 elements")
        print("\n-- layout edge cases --")

    cases = [
        16384,          # exactly world_size * align, no ragged tail
        16385,          # one element past; forces the mask path
        16383,          # one short
        106560711,      # the real FastWAM bucket numel (odd, not 8-divisible)
        110167040,      # 220 MB bf16, the size the gate benchmarked
    ]
    for i, n in enumerate(cases):
        check(n, rank, world_size, index=i)

    if rank == 0:
        print("\n-- dynamic range --")
    for i, s in enumerate([1e-6, 1.0, 1e4]):
        check(1 << 20, rank, world_size, index=100 + i, scale=s)

    if rank == 0:
        print("\n-- fp32 buckets --")
    check(1 << 22, rank, world_size, dtype=torch.float32, index=200)

    if rank == 0:
        print("\n-- small-bucket AllReduce fallback (must be bf16-exact) --")
    configure(min_mib=1024)
    err = check(1 << 16, rank, world_size, index=300)
    assert err < 5e-3, f"fallback path should be bf16-accurate, got {err:.3e}"
    configure(min_mib=0)

    if rank == 0:
        print("\n-- over-budget scratch degrades, does not raise --")
    # A bucket layout we cannot afford must send at full precision, not kill the
    # job. Squeeze the budget to ~1 KiB so any real bucket trips it.
    reset_scratch()
    configure(min_mib=0, max_scratch_gb=1e-6)
    err = check(1 << 22, rank, world_size, index=350)
    assert err < 5e-3, f"over-budget path should be bf16-accurate, got {err:.3e}"
    configure(min_mib=0)
    reset_scratch()

    if rank == 0:
        print("\n-- int64 offset overflow --")
        print("   DDP hands FastWAM a single 6.02e9-element bucket; the fused")
        print("   uint8 buffer is then >2^31 bytes, so int32 indexing wraps.")
    check_big(2_200_000_000, rank, world_size, index=400)

    if rank == 0:
        print("\n-- repeat determinism (scratch reuse across steps) --")
    errs = [check(106560711, rank, world_size, index=3) for _ in range(3)]
    assert max(errs) - min(errs) < 1e-12, "scratch reuse changed the result"

    reset_scratch()
    if rank == 0:
        print("\nOK")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
