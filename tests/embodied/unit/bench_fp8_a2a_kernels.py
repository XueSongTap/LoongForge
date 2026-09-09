# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

"""Standalone timing for the four fp8_a2a kernels.

The training A/B showed backward-compute going 578 -> 812 ms while the wire
bytes dropped 45%, so the kernels -- not the collectives -- are the cost. This
measures each kernel's achieved HBM bandwidth at the real DDP bucket size and
sweeps the tile shape, without paying 6 minutes per data point.

    python bench_fp8_a2a_kernels.py
"""

import os
import sys

import torch

sys.path.insert(0, os.environ.get("LOONGFORGE_PATH", "."))

import loongforge.embodied.distributed.ddp_utils.fp8_a2a_comm as K  # noqa: E402

NUMEL = 106_560_711     # the real FastWAM steady-state bucket
WORLD = 8


def timed(fn, iters=20, warmup=5):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    for _ in range(iters):
        fn()
    end.record()
    torch.cuda.synchronize()
    return start.elapsed_time(end) / iters


def run(block, nb):
    K.NUM_BLOCKS_PER_TILE = nb
    align = block * nb
    per_rank = (NUMEL + WORLD - 1) // WORLD
    S = (per_rank + align - 1) // align * align
    chunk_u8 = S + 4 * (S // block)

    grad = torch.randn(NUMEL, device="cuda", dtype=torch.bfloat16)
    send = torch.empty(WORLD * chunk_u8, dtype=torch.uint8, device="cuda")
    recv = torch.empty(WORLD * chunk_u8, dtype=torch.uint8, device="cuda")
    shard = torch.empty(S, dtype=torch.bfloat16, device="cuda")

    # Bytes each kernel must move, at minimum, through HBM.
    q_bytes = NUMEL * 2 + WORLD * chunk_u8          # read bf16, write fp8+scale
    r_bytes = WORLD * chunk_u8 + S * 2              # read all chunks, write shard
    qs_bytes = S * 2 + chunk_u8
    d_bytes = WORLD * chunk_u8 + NUMEL * 2

    rows = []
    for name, fn, nbytes in (
        ("quantize_full",
         lambda: K.quantize_chunks(grad, send, NUMEL, S, chunk_u8, WORLD, block),
         q_bytes),
        ("dequant_reduce",
         lambda: K.dequant_reduce(recv, shard, S, chunk_u8, WORLD, block),
         r_bytes),
        ("quantize_shard",
         lambda: K.quantize_chunks(shard, send[:chunk_u8], S, S, chunk_u8, 1, block),
         qs_bytes),
        ("dequant_scatter",
         lambda: K.dequant_scatter(recv, grad, NUMEL, S, chunk_u8, WORLD, block),
         d_bytes),
    ):
        ms = timed(fn)
        rows.append((name, ms, nbytes / ms / 1e6))

    total_ms = sum(r[1] for r in rows)
    print(f"BLOCK={block:4d} NB={nb:3d} tile={align:6d} el  "
          f"total={total_ms:7.2f} ms  " +
          "  ".join(f"{n}={ms:6.2f}({gb:5.0f}GB/s)" for n, ms, gb in rows))
    del grad, send, recv, shard
    torch.cuda.empty_cache()
    return total_ms


def main():
    torch.cuda.set_device(0)
    name = torch.cuda.get_device_name(0)
    print(f"{name}, bucket numel={NUMEL}, world={WORLD}")
    print("per-step cost for the whole model = total x (6.02e9 / numel) "
          f"= total x {6_020_710_599 / NUMEL:.1f}\n")

    best = None
    for block in (128, 256):
        for nb in (8, 16, 32, 64, 128):
            if block * nb > 32768:      # Triton tile register limit
                continue
            try:
                ms = run(block, nb)
            except Exception as exc:
                print(f"BLOCK={block:4d} NB={nb:3d}  FAILED: {type(exc).__name__}")
                continue
            if best is None or ms < best[0]:
                best = (ms, block, nb)
        print()

    ms, block, nb = best
    scale = 6_020_710_599 / NUMEL
    print(f"best: BLOCK={block} NB={nb} -> {ms:.2f} ms/bucket, "
          f"{ms * scale:.0f} ms/step for the full model")
    print(f"current default is BLOCK={K.DEFAULT_BLOCK} NB=8")


if __name__ == "__main__":
    main()
