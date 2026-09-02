# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the sensitive-information scanner's public interfaces."""

import importlib.util
from pathlib import Path
import sys

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ci" / "sensitive_scan.py"
SPEC = importlib.util.spec_from_file_location("sensitive_scan", MODULE_PATH)
assert SPEC and SPEC.loader
sensitive_scan = importlib.util.module_from_spec(SPEC)
sys.modules["sensitive_scan"] = sensitive_scan
SPEC.loader.exec_module(sensitive_scan)


def _email() -> str:
    return "reviewer" + "@" + "baidu" + ".com"


def test_ci_summary_omits_locations_and_snippets(capsys):
    findings = [
        sensitive_scan.Finding(
            rule="corp-email",
            severity="error",
            title="Corporate email address",
            location="private/path.txt",
            line=7,
            snippet=_email(),
            hint="remove",
        ),
        sensitive_scan.Finding(
            rule="internal-cluster-path",
            severity="warn",
            title="Internal path",
            location="runner/config.env",
            line=11,
            snippet="/private/runner/path",
            hint="replace",
        ),
    ]

    sensitive_scan.report_ci_summary(findings, strict=True)
    output = capsys.readouterr().out

    assert "corp-email (1)" in output
    assert "internal-cluster-path (1)" in output
    assert "private/path.txt" not in output
    assert "runner/config.env" not in output
    assert _email() not in output
    assert "/private/runner/path" not in output
    assert "FAIL (2 blocking finding(s))" in output


def test_ci_summary_clean_result(capsys):
    sensitive_scan.report_ci_summary([], strict=True)
    assert capsys.readouterr().out == (
        "sensitive-scan: 0 error(s), 0 warning(s), 0 total\n"
        "sensitive-scan: PASS\n"
    )


def test_history_fixture_is_scanned_without_printing_private_values(monkeypatch, capsys):
    history_email = _email()
    deleted_name = "deleted-history-fixture.txt"

    def fake_git(*args: str, check: bool = True) -> str:
        if args[:2] == ("log", "--all") and "<%ae>" in args[-1]:
            return f"Reviewer {history_email}\n"
        if args[:2] == ("log", "--all"):
            return "release notes\n"
        if args[0] == "tag":
            return ""
        if args[0] == "branch":
            return "main\n"
        if args[:2] == ("ls-tree", "-r"):
            return f"{deleted_name}\n"
        if args[:2] == ("show", f"HEAD:{deleted_name}"):
            return f"owner = '{history_email}'\n"
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(sensitive_scan, "git", fake_git)
    monkeypatch.setattr(sensitive_scan, "candidate_files", lambda _: [])
    rules = sensitive_scan.compile_rules(["corp-email"])
    findings = sensitive_scan.scan_history(rules, sensitive_scan.compile_allowlist())

    assert len(findings) == 2
    assert {finding.location for finding in findings} == {
        "git:authors",
        f"git:HEAD:{deleted_name}",
    }
    sensitive_scan.report_ci_summary(findings, strict=True)
    output = capsys.readouterr().out
    assert history_email not in output
    assert deleted_name not in output
    assert "corp-email (2)" in output


def test_absolute_path_filter_is_normalized(monkeypatch, tmp_path):
    root = str(tmp_path)
    absolute = str(Path(root) / "tests")
    assert sensitive_scan.normalize_path_filters([absolute], root) == ["tests"]


def test_path_filter_outside_repository_is_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        sensitive_scan.normalize_path_filters([str(tmp_path.parent)], str(tmp_path))
    assert exc.value.code == 2
