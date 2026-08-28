#!/usr/bin/env python3
# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

"""Render a regression suite results.json as a compact markdown table.

The embodied regression framework writes per-model pass/fail state, failed
baseline comparisons, warnings, and per-iteration metrics to results.json.
This script turns that file into a short markdown summary suitable for a
pull request check run output. It never fails the job: any input problem
produces a fallback line instead of an error exit.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Keep the rendered table small enough for a check run output even when a
# suite runs every configured model.
MAX_FIELD_CHARS = 200


def _clip(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _loss_series(metrics: list[dict[str, Any]]) -> list[tuple[int, str, float]]:
    losses: list[tuple[int, str, float]] = []
    for record in metrics or []:
        iteration = record.get("iteration", 0)
        for key, value in record.items():
            if "loss" not in key or key == "loss_scale":
                continue
            try:
                losses.append((int(iteration), key, float(value)))
            except (TypeError, ValueError):
                continue
    return losses


def _render_model_row(result: dict[str, Any]) -> str:
    name = str(result.get("model_name", "?"))
    passed = result.get("passed", False)
    verdict = "PASS" if passed else "FAIL"

    losses = _loss_series(result.get("metrics", []))
    if losses:
        first_key, first_value = losses[0][1], losses[0][2]
        last_key, last_value = losses[-1][1], losses[-1][2]
        if first_key == last_key:
            loss_text = f"{first_key}: {first_value:.6g} → {last_value:.6g}"
        else:
            loss_text = (
                f"{first_key}: {first_value:.6g}; {last_key}: {last_value:.6g}"
            )
    else:
        loss_text = "-"

    failed_metrics = "<br>".join(result.get("failed_metrics") or [])
    warnings = "<br>".join(result.get("warnings") or [])
    error = str(result.get("error") or "").strip()

    notes: list[str] = []
    if failed_metrics:
        notes.append(f"failed: {_clip(failed_metrics)}")
    if warnings:
        notes.append(f"warn: {_clip(warnings)}")
    if error:
        notes.append(f"error: {_clip(error)}")
    notes_text = "<br>".join(notes) if notes else "-"

    return f"| {name} | {verdict} | {loss_text} | {notes_text} |"


def render(summary: dict[str, Any]) -> str:
    results = summary.get("results") or []
    chip = str(summary.get("chip") or "-")
    lines = [
        f"Regression results (chip `{chip}`):",
        "",
        "| Model | Result | Loss (first → last) | Notes |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(_render_model_row(result) for result in results)
    passed = sum(1 for result in results if result.get("passed"))
    lines.append("")
    lines.append(f"{passed}/{len(results)} models passed baseline comparison.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_file", help="path to the suite results.json")
    args = parser.parse_args()

    try:
        with open(args.results_file, encoding="utf-8") as handle:
            summary = json.load(handle)
        if not isinstance(summary, dict) or not isinstance(
            summary.get("results"), list
        ):
            raise ValueError("unexpected results.json structure")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        # Report the parsing problem without failing the job; the check run
        # still carries the suite-level pass/fail state.
        print(f"Suite detail unavailable ({type(exc).__name__}).")
        return 0

    print(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
