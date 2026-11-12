"""`python -m taxigraph_spike check --mode smoke|real`.

Orchestrates the eligible chain for the requested mode and writes one
structured report (out/report.json for smoke, or the manifest-relative
path for real). Never upgrades a partial result to a pass.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import evaluation, gtfs_export, otp_runner, prerequisites, real_manifest, report, synthetic_fixture, validator_runner
from .graphql_client import post_query, save_introspection

BASE_DIR = Path(__file__).resolve().parents[2]
TOOLS_MANIFEST_PATH = BASE_DIR / "tools-manifest.json"
OUT_DIR = BASE_DIR / "out"
GRAPHQL_URL = f"http://localhost:{otp_runner.LOOPBACK_PORT}{otp_runner.GRAPHQL_PATH}"
PLAN_QUERY_PATH = BASE_DIR / "queries" / "plan-query.graphql"


SOFT_OPTIONAL_TOOLS = {"tool:osm_extract"}


def _post_plan_query(query: str, variables: dict) -> dict:
    """Return OTP's data, or raise so evaluate_cases records the case as an error.

    An empty dict would be scored as "no_journey", letting negative controls
    pass while OTP is down or the schema has drifted.
    """

    result = post_query(GRAPHQL_URL, query, variables)
    if result.status != "ok" or result.data is None:
        raise RuntimeError(f"{result.status}: {result.errors}")
    return result.data


def run_smoke(base_dir: Path = BASE_DIR) -> report.CheckReport:
    details: dict = {}

    prereq = prerequisites.run_prerequisite_checks(base_dir, TOOLS_MANIFEST_PATH)
    details["prerequisites"] = [c.__dict__ for c in prereq.checks]

    network = synthetic_fixture.load_synthetic_network(synthetic_fixture.default_fixture_path())
    gtfs_dir = OUT_DIR / "gtfs"
    export_result = gtfs_export.build_gtfs(network, gtfs_dir)
    details["gtfs_export"] = {
        "zip_path": str(export_result.zip_path),
        "warnings": export_result.warnings,
    }

    required_checks = [c for c in prereq.checks if c.name not in SOFT_OPTIONAL_TOOLS]
    if not all(c.ok for c in required_checks):
        details["blocked_reason"] = "missing prerequisites; GTFS export ran, OTP/validator steps skipped"
        return report.CheckReport(
            mode="smoke",
            software_status=report.STATUS_BLOCKED,
            real_data_status=report.STATUS_NOT_APPLICABLE,
            rights_status=report.STATUS_NOT_APPLICABLE,
            journey_validation_status=report.STATUS_NOT_RUN,
            details=details,
        )

    manifest = prerequisites.load_tools_manifest(TOOLS_MANIFEST_PATH)
    java_binary = prerequisites.resolve_java_binary(base_dir, manifest)
    validator_jar = base_dir / manifest["tools"]["gtfs_validator"]["local_path"]
    otp_jar = base_dir / manifest["tools"]["otp"]["local_path"]
    osm_pbf_path = base_dir / manifest["tools"]["osm_extract"]["local_path"]
    osm_pbf = osm_pbf_path if osm_pbf_path.is_file() else None
    if osm_pbf is None:
        details["street_data_status"] = (
            "no pinned OSM extract present; building a GTFS-only graph. Cases that need real street "
            "topology (e.g. false_transfer_across_barrier) are not meaningfully validated by this run."
        )

    validator_result = validator_runner.run_gtfs_validator(
        validator_jar, export_result.zip_path, OUT_DIR / "validator", java_binary=java_binary
    )
    details["validator"] = validator_result.__dict__
    if validator_result.status != "ok":
        return report.CheckReport(
            mode="smoke",
            software_status=report.STATUS_BLOCKED if validator_result.status == "missing_prerequisite" else report.STATUS_FAIL,
            real_data_status=report.STATUS_NOT_APPLICABLE,
            rights_status=report.STATUS_NOT_APPLICABLE,
            journey_validation_status=report.STATUS_NOT_RUN,
            details=details,
        )

    build_dir = OUT_DIR / "otp-build"
    graph_dir = OUT_DIR / "otp-graph"
    build_result = otp_runner.build_graph(
        otp_jar, export_result.zip_path, build_dir, graph_dir, osm_pbf=osm_pbf, java_binary=java_binary
    )
    details["otp_build"] = {"status": build_result.status, "detail": build_result.detail}
    if build_result.status != "ok":
        return report.CheckReport(
            mode="smoke",
            software_status=report.STATUS_BLOCKED if build_result.status == "missing_prerequisite" else report.STATUS_FAIL,
            real_data_status=report.STATUS_NOT_APPLICABLE,
            rights_status=report.STATUS_NOT_APPLICABLE,
            journey_validation_status=report.STATUS_NOT_RUN,
            details=details,
        )

    server_log = OUT_DIR / "otp-server.log"
    proc = otp_runner.start_server(otp_jar, graph_dir, server_log, java_binary=java_binary)
    try:
        ready = otp_runner.wait_for_ready(f"http://localhost:{otp_runner.LOOPBACK_PORT}", proc=proc)
        if not ready:
            details["otp_server"] = f"did not become ready; see {server_log}"
            return report.CheckReport(
                mode="smoke",
                software_status=report.STATUS_FAIL,
                real_data_status=report.STATUS_NOT_APPLICABLE,
                rights_status=report.STATUS_NOT_APPLICABLE,
                journey_validation_status=report.STATUS_NOT_RUN,
                details=details,
            )

        introspection = save_introspection(GRAPHQL_URL, OUT_DIR / "otp-schema" / "introspection.json")
        details["introspection_status"] = introspection.status

        cases = network["positive_cases"] + network["negative_controls"]
        eval_result = evaluation.evaluate_cases(PLAN_QUERY_PATH, _post_plan_query, cases)
        details["evaluation"] = {
            "status": eval_result.status,
            "detail": eval_result.detail,
            "outcomes": [o.__dict__ for o in eval_result.outcomes],
        }

        journey_status = {
            "ok": report.STATUS_PASS,
            "fail": report.STATUS_FAIL,
            "query_not_verified": report.STATUS_BLOCKED,
            "otp_unavailable": report.STATUS_BLOCKED,
        }[eval_result.status]

        software_status = report.STATUS_PASS if journey_status == report.STATUS_PASS else report.STATUS_FAIL
        if journey_status == report.STATUS_BLOCKED:
            software_status = report.STATUS_BLOCKED

        return report.CheckReport(
            mode="smoke",
            software_status=software_status,
            real_data_status=report.STATUS_NOT_APPLICABLE,
            rights_status=report.STATUS_NOT_APPLICABLE,
            journey_validation_status=journey_status,
            details=details,
        )
    finally:
        otp_runner.stop_server(proc)


def run_real(manifest_path: Path, base_dir: Path = BASE_DIR) -> report.CheckReport:
    details: dict = {}

    if not manifest_path.is_file():
        details["missing"] = [f"manifest file not found at {manifest_path}"]
        return report.CheckReport(
            mode="real",
            software_status=report.STATUS_NOT_RUN,
            real_data_status=report.STATUS_DATA_BLOCKED,
            rights_status=report.STATUS_DATA_BLOCKED,
            journey_validation_status=report.STATUS_NOT_RUN,
            details=details,
        )

    manifest = real_manifest.load_manifest(manifest_path)
    validation = real_manifest.validate_real_manifest(manifest)
    details["manifest_validation"] = {"status": validation.status, "missing": validation.missing}

    if not validation.eligible:
        rights_missing = any("source_rights_reference" in item for item in validation.missing)
        return report.CheckReport(
            mode="real",
            software_status=report.STATUS_NOT_RUN,
            real_data_status=report.STATUS_DATA_BLOCKED,
            rights_status=report.STATUS_DATA_BLOCKED if rights_missing else report.STATUS_NOT_APPLICABLE,
            journey_validation_status=report.STATUS_NOT_RUN,
            details=details,
        )

    # Contract satisfied, but real canonical -> GTFS projection and OTP
    # evaluation are not implemented in this spike yet (ROADMAP task 3+).
    details["blocked_reason"] = "real manifest contract satisfied; real export/evaluation pipeline not yet implemented"
    return report.CheckReport(
        mode="real",
        software_status=report.STATUS_NOT_RUN,
        real_data_status=report.STATUS_PASS,
        rights_status=report.STATUS_PASS,
        journey_validation_status=report.STATUS_BLOCKED,
        details=details,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="taxigraph_spike")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--mode", choices=["smoke", "real"], required=True)
    check_parser.add_argument("--manifest", type=Path, default=BASE_DIR / "local" / "real-manifest.json")

    args = parser.parse_args(argv)

    if args.command == "check":
        if args.mode == "smoke":
            result = run_smoke()
            out_path = OUT_DIR / "report.json"
        else:
            result = run_real(args.manifest)
            out_path = OUT_DIR / "real-report.json"

        report.write_report(result, out_path)
        print(f"wrote {out_path}")
        print(
            f"software={result.software_status} real_data={result.real_data_status} "
            f"rights={result.rights_status} journey_validation={result.journey_validation_status}"
        )
        return report.decide_exit_code(result)

    return 2


if __name__ == "__main__":
    sys.exit(main())
