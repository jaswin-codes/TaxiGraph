import json
from pathlib import Path

from taxigraph_spike import prerequisites


def test_check_java_version_missing_binary(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(prerequisites.subprocess, "run", fake_run)
    result = prerequisites.check_java_version(min_major=25)
    assert result.ok is False
    assert "not found" in result.detail


def test_check_java_version_too_old(monkeypatch):
    class FakeProc:
        stdout = ""
        stderr = 'openjdk version "17.0.2" 2022-01-18\n'

    monkeypatch.setattr(prerequisites.subprocess, "run", lambda *a, **k: FakeProc())
    result = prerequisites.check_java_version(min_major=25)
    assert result.ok is False
    assert "java 17" in result.detail


def test_check_java_version_ok(monkeypatch):
    class FakeProc:
        stdout = ""
        stderr = 'openjdk version "25" 2025-09-16\n'

    monkeypatch.setattr(prerequisites.subprocess, "run", lambda *a, **k: FakeProc())
    result = prerequisites.check_java_version(min_major=25)
    assert result.ok is True


def test_check_tool_artifact_missing_file(tmp_path: Path):
    spec = {"local_path": "local/tools/missing.jar", "version": "1.0"}
    result = prerequisites.check_tool_artifact("thing", spec, tmp_path)
    assert result.ok is False
    assert "missing" in result.detail


def test_check_tool_artifact_no_pinned_checksum(tmp_path: Path):
    tool_path = tmp_path / "local" / "tools" / "thing.jar"
    tool_path.parent.mkdir(parents=True)
    tool_path.write_bytes(b"fake jar bytes")

    spec = {"local_path": "local/tools/thing.jar", "sha256": None}
    result = prerequisites.check_tool_artifact("thing", spec, tmp_path)
    assert result.ok is False
    assert "no sha256 pinned" in result.detail


def test_check_tool_artifact_checksum_mismatch(tmp_path: Path):
    tool_path = tmp_path / "local" / "tools" / "thing.jar"
    tool_path.parent.mkdir(parents=True)
    tool_path.write_bytes(b"fake jar bytes")

    spec = {"local_path": "local/tools/thing.jar", "sha256": "0" * 64}
    result = prerequisites.check_tool_artifact("thing", spec, tmp_path)
    assert result.ok is False
    assert "checksum mismatch" in result.detail


def test_check_tool_artifact_checksum_ok(tmp_path: Path):
    tool_path = tmp_path / "local" / "tools" / "thing.jar"
    tool_path.parent.mkdir(parents=True)
    tool_path.write_bytes(b"fake jar bytes")
    actual_sha256 = prerequisites._sha256_of(tool_path)

    spec = {"local_path": "local/tools/thing.jar", "sha256": actual_sha256}
    result = prerequisites.check_tool_artifact("thing", spec, tmp_path)
    assert result.ok is True


def test_run_prerequisite_checks_missing_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(prerequisites.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    report = prerequisites.run_prerequisite_checks(tmp_path, tmp_path / "no-manifest.json")
    assert report.ok is False
    assert any("tools manifest" in m for m in report.missing)


def test_run_prerequisite_checks_reads_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(prerequisites.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    manifest_path = tmp_path / "tools-manifest.json"
    manifest_path.write_text(json.dumps({"tools": {"otp": {"local_path": "local/tools/otp.jar", "sha256": None}}}))

    report = prerequisites.run_prerequisite_checks(tmp_path, manifest_path)
    assert report.ok is False
    names = [c.name for c in report.checks]
    assert "tool:otp" in names


def test_check_tool_artifact_checksum_ok_when_pinned_uppercase(tmp_path: Path):
    tool_path = tmp_path / "local" / "tools" / "thing.jar"
    tool_path.parent.mkdir(parents=True)
    tool_path.write_bytes(b"fake jar bytes")
    pinned = prerequisites._sha256_of(tool_path).upper()  # as printed by PowerShell's Get-FileHash

    spec = {"local_path": "local/tools/thing.jar", "sha256": pinned}
    result = prerequisites.check_tool_artifact("thing", spec, tmp_path)
    assert result.ok is True
