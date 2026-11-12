"""Prerequisite and pinned-artifact checks.

Nothing here downloads or installs anything. It only inspects what is
already on the machine and compares it against docs/SOL-HANDOFF.md's pins,
so `check` can fail closed with a specific missing item instead of a stack
trace from a missing binary.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

MIN_JAVA_MAJOR = 25
MIN_PYTHON = (3, 13)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class PrerequisiteReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def missing(self) -> list[str]:
        return [c.detail for c in self.checks if not c.ok]


def check_python_version(min_version: tuple[int, int] = MIN_PYTHON) -> CheckResult:
    import sys

    actual = (sys.version_info.major, sys.version_info.minor)
    ok = actual >= min_version
    detail = f"python {actual[0]}.{actual[1]} (need >= {min_version[0]}.{min_version[1]})"
    return CheckResult("python_version", ok, detail)


def check_java_version(java_binary: str = "java", min_major: int = MIN_JAVA_MAJOR) -> CheckResult:
    try:
        proc = subprocess.run(
            [java_binary, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return CheckResult("java_version", False, f"{java_binary} not found")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult("java_version", False, f"{java_binary} -version failed: {exc}")

    output = proc.stderr + proc.stdout
    match = re.search(r'version "(\d+)', output)
    if not match:
        return CheckResult("java_version", False, f"could not parse java version from: {output.strip()!r}")

    major = int(match.group(1))
    ok = major >= min_major
    detail = f"java {major} (need >= {min_major}) via {java_binary}"
    return CheckResult("java_version", ok, detail)


def resolve_java_binary(base_dir: Path, manifest: dict) -> str:
    """Prefer the pinned local JDK; fall back to whatever `java` is on PATH."""

    pinned = manifest.get("java", {}).get("java_binary")
    if pinned and (base_dir / pinned).is_file():
        return str((base_dir / pinned).resolve())
    return "java"


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_tool_artifact(name: str, spec: dict, base_dir: Path) -> CheckResult:
    local_path = base_dir / spec["local_path"]
    if not local_path.is_file():
        return CheckResult(
            f"tool:{name}",
            False,
            f"{name}: missing at {spec['local_path']} (pin: {spec.get('version', 'unpinned')})",
        )

    expected_sha256 = spec.get("sha256")
    if not expected_sha256:
        return CheckResult(
            f"tool:{name}",
            False,
            f"{name}: present at {spec['local_path']} but no sha256 pinned in the manifest yet",
        )

    actual_sha256 = _sha256_of(local_path)
    # Hex digests are case-insensitive; PowerShell's Get-FileHash prints uppercase.
    if actual_sha256 != expected_sha256.strip().lower():
        return CheckResult(
            f"tool:{name}",
            False,
            f"{name}: checksum mismatch (expected {expected_sha256}, got {actual_sha256})",
        )

    return CheckResult(f"tool:{name}", True, f"{name}: {spec['local_path']} checksum verified")


def load_tools_manifest(manifest_path: Path) -> dict:
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_prerequisite_checks(base_dir: Path, manifest_path: Path) -> PrerequisiteReport:
    checks = [check_python_version()]

    if not manifest_path.is_file():
        checks.append(CheckResult("tools_manifest", False, f"missing tools manifest at {manifest_path}"))
        checks.append(check_java_version())
        return PrerequisiteReport(checks)

    manifest = load_tools_manifest(manifest_path)
    checks.append(check_java_version(resolve_java_binary(base_dir, manifest), manifest.get("java", {}).get("min_major_version", MIN_JAVA_MAJOR)))
    for name, spec in manifest.get("tools", {}).items():
        checks.append(check_tool_artifact(name, spec, base_dir))

    return PrerequisiteReport(checks)
