import json
import subprocess
from pathlib import Path

from taxigraph_spike import validator_runner


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    jar = tmp_path / "validator.jar"
    feed = tmp_path / "feed.zip"
    jar.write_bytes(b"")
    feed.write_bytes(b"")
    return jar, feed, tmp_path / "out"


def _fake_run(report: str | None, returncode: int = 0):
    def fake(args, timeout=None):
        if report is not None:
            out_dir = Path(args[args.index("-o") + 1])
            (out_dir / "report.json").write_text(report, encoding="utf-8")
        return subprocess.CompletedProcess(args, returncode, stdout="", stderr="boom")

    return fake


def test_missing_jar_is_missing_prerequisite(tmp_path: Path):
    result = validator_runner.run_gtfs_validator(tmp_path / "nope.jar", tmp_path / "feed.zip", tmp_path / "out")
    assert result.status == "missing_prerequisite"


def test_counts_error_and_warning_notice_types(monkeypatch, tmp_path: Path):
    notices = [{"severity": "ERROR"}, {"severity": "WARNING"}, {"severity": "WARNING"}, {"severity": "INFO"}]
    monkeypatch.setattr(validator_runner, "run_hidden", _fake_run(json.dumps({"notices": notices})))
    jar, feed, out_dir = _inputs(tmp_path)

    result = validator_runner.run_gtfs_validator(jar, feed, out_dir)

    assert result.status == "validation_failed"
    assert (result.error_count, result.warning_count) == (1, 2)


def test_stale_report_is_not_reused_when_validator_writes_nothing(monkeypatch, tmp_path: Path):
    jar, feed, out_dir = _inputs(tmp_path)
    out_dir.mkdir()
    (out_dir / "report.json").write_text(json.dumps({"notices": []}), encoding="utf-8")
    monkeypatch.setattr(validator_runner, "run_hidden", _fake_run(None, returncode=1))

    result = validator_runner.run_gtfs_validator(jar, feed, out_dir)

    assert result.status == "error"


def test_invalid_report_json_is_an_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(validator_runner, "run_hidden", _fake_run("{not json"))
    jar, feed, out_dir = _inputs(tmp_path)

    result = validator_runner.run_gtfs_validator(jar, feed, out_dir)

    assert result.status == "error"


def test_timeout_is_an_error(monkeypatch, tmp_path: Path):
    def fake(args, timeout=None):
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(validator_runner, "run_hidden", fake)
    jar, feed, out_dir = _inputs(tmp_path)

    assert validator_runner.run_gtfs_validator(jar, feed, out_dir).status == "error"
