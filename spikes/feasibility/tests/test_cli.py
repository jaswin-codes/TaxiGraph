import json
from pathlib import Path

import pytest

from taxigraph_spike import cli, evaluation, prerequisites
from taxigraph_spike.graphql_client import GraphQLResult


@pytest.mark.parametrize("status", ["graphql_error", "otp_unavailable"])
def test_otp_errors_do_not_pass_negative_controls(monkeypatch, tmp_path: Path, status):
    monkeypatch.setattr(cli, "post_query", lambda *a, **k: GraphQLResult(status, errors=[{"message": "boom"}]))
    query_path = tmp_path / "plan-query.graphql"
    query_path.write_text("query Plan { planConnection { edges { node { start } } } }")
    negative = {
        "id": "neg",
        "origin_stop_id": "SYN_STOP_3",
        "destination_stop_id": "SYN_STOP_1",
        "expected_result": "no_journey",
    }

    result = evaluation.evaluate_cases(query_path, cli._post_plan_query, [negative])

    assert result.status == "fail"
    assert result.outcomes[0].actual_result == "error"
    assert status in result.outcomes[0].detail


def test_smoke_reports_blocked_when_java_missing(monkeypatch):
    monkeypatch.setattr(
        prerequisites,
        "check_java_version",
        lambda *args, **kwargs: prerequisites.CheckResult("java_version", False, "java not found on PATH"),
    )

    exit_code = cli.main(["check", "--mode", "smoke"])

    assert exit_code == 2
    report_path = cli.OUT_DIR / "report.json"
    assert report_path.is_file()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["software_status"] == "blocked"
    assert data["journey_validation_status"] == "not_run"
    # GTFS export still ran even though OTP/validator steps were skipped.
    assert Path(data["details"]["gtfs_export"]["zip_path"]).is_file()


def test_real_mode_blocked_without_manifest(tmp_path: Path):
    missing_manifest = tmp_path / "does-not-exist.json"

    exit_code = cli.main(["check", "--mode", "real", "--manifest", str(missing_manifest)])

    assert exit_code == 2
    report_path = cli.OUT_DIR / "real-report.json"
    assert report_path.is_file()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["real_data_status"] == "data_blocked"
    assert data["rights_status"] == "data_blocked"


def test_real_mode_blocked_with_incomplete_manifest(tmp_path: Path):
    manifest_path = tmp_path / "real-manifest.json"
    manifest_path.write_text(json.dumps({"dataset_version": "2026-09-01"}))

    exit_code = cli.main(["check", "--mode", "real", "--manifest", str(manifest_path)])

    assert exit_code == 2
    data = json.loads((cli.OUT_DIR / "real-report.json").read_text(encoding="utf-8"))
    assert data["real_data_status"] == "data_blocked"
    assert data["details"]["manifest_validation"]["status"] == "data_blocked"
    assert "source_rights_reference" in data["details"]["manifest_validation"]["missing"]


def test_run_smoke_uses_base_dir_for_inputs_and_outputs(tmp_path: Path):
    # An empty base_dir has no tools-manifest.json, so the run is blocked after the GTFS export.
    result = cli.run_smoke(tmp_path)

    assert result.software_status == "blocked"
    assert (tmp_path / "out" / "gtfs" / "feed.zip").is_file()
