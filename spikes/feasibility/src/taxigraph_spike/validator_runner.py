"""Wrapper around the pinned MobilityData GTFS validator CLI.

Never implements GTFS parsing/validation itself. If the pinned jar is not
present, this reports `missing_prerequisite` instead of letting a
FileNotFoundError propagate as an unrelated crash.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .process_utils import run_hidden


@dataclass(frozen=True)
class ValidatorResult:
    status: str  # "ok" | "validation_failed" | "missing_prerequisite" | "error"
    detail: str
    error_count: int = 0
    warning_count: int = 0
    notices: list[dict[str, Any]] = field(default_factory=list)
    report_path: Path | None = None


def run_gtfs_validator(
    jar_path: Path,
    feed_zip: Path,
    out_dir: Path,
    java_binary: str = "java",
    timeout_seconds: int = 300,
) -> ValidatorResult:
    if not jar_path.is_file():
        return ValidatorResult("missing_prerequisite", f"validator jar not found at {jar_path}")
    if not feed_zip.is_file():
        return ValidatorResult("error", f"feed zip not found at {feed_zip}")

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.json"
    # A report left by an earlier run must never be mistaken for this run's result.
    report_path.unlink(missing_ok=True)
    args = [
        java_binary,
        "-jar",
        str(jar_path.resolve()),
        "-i",
        str(feed_zip.resolve()),
        "-o",
        str(out_dir.resolve()),
    ]

    try:
        proc = run_hidden(args, timeout=timeout_seconds)
    except FileNotFoundError:
        return ValidatorResult("missing_prerequisite", f"{java_binary} not found")
    except subprocess.TimeoutExpired:
        return ValidatorResult("error", f"validator did not finish within {timeout_seconds}s")

    if not report_path.is_file():
        return ValidatorResult(
            "error",
            f"validator exited {proc.returncode} but wrote no report.json; stderr: {proc.stderr[:500]!r}",
        )

    try:
        with report_path.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
    except ValueError as exc:
        return ValidatorResult("error", f"report.json is not valid JSON: {exc}")
    if not isinstance(report, dict):
        return ValidatorResult("error", "report.json is not a JSON object")

    notices = report.get("notices", [])
    error_count = sum(1 for n in notices if n.get("severity") == "ERROR")
    warning_count = sum(1 for n in notices if n.get("severity") == "WARNING")

    status = "validation_failed" if error_count > 0 else "ok"
    detail = f"{error_count} error notice types, {warning_count} warning notice types"
    return ValidatorResult(status, detail, error_count, warning_count, notices, report_path)
