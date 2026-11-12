import csv
import zipfile
from pathlib import Path

import pytest

from taxigraph_spike import gtfs_export, synthetic_fixture


@pytest.fixture()
def network():
    return synthetic_fixture.load_synthetic_network(synthetic_fixture.default_fixture_path())


def test_build_gtfs_writes_expected_tables(tmp_path: Path, network):
    result = gtfs_export.build_gtfs(network, tmp_path / "gtfs")

    for table in gtfs_export.GTFS_TABLES:
        assert (result.out_dir / table).is_file(), table

    assert not (result.out_dir / "fare_attributes.txt").exists()
    assert not (result.out_dir / "fare_rules.txt").exists()


def test_build_gtfs_rejects_non_synthetic_network(tmp_path: Path):
    with pytest.raises(ValueError, match="synthetic"):
        gtfs_export.build_gtfs({"provenance": {"kind": "real"}}, tmp_path / "gtfs")


def test_frequencies_are_non_exact(tmp_path: Path, network):
    result = gtfs_export.build_gtfs(network, tmp_path / "gtfs")
    with (result.out_dir / "frequencies.txt").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["exact_times"] == "0" for row in rows)


def test_calendar_has_finite_dates(tmp_path: Path, network):
    result = gtfs_export.build_gtfs(network, tmp_path / "gtfs")
    with (result.out_dir / "calendar.txt").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["start_date"] == network["service"]["start_date"]
    assert rows[0]["end_date"] == network["service"]["end_date"]


def test_stop_times_trace_to_fixture_offsets(tmp_path: Path, network):
    result = gtfs_export.build_gtfs(network, tmp_path / "gtfs")
    with (result.out_dir / "stop_times.txt").open(newline="", encoding="utf-8") as handle:
        rows = {(row["trip_id"], int(row["stop_sequence"])): row for row in csv.DictReader(handle)}

    trip = next(t for t in network["trips"] if t["trip_id"] == "SYN_A_OUT")
    for sequence, (stop_id, offset) in enumerate(zip(trip["stops"], trip["stop_offsets_seconds"]), start=1):
        row = rows[("SYN_A_OUT", sequence)]
        assert row["stop_id"] == stop_id
        assert row["arrival_time"] == gtfs_export._seconds_to_gtfs_time(offset)


def test_zip_contains_all_tables(tmp_path: Path, network):
    result = gtfs_export.build_gtfs(network, tmp_path / "gtfs")
    with zipfile.ZipFile(result.zip_path) as archive:
        names = set(archive.namelist())
    assert names == set(gtfs_export.GTFS_TABLES)


def test_id_map_written(tmp_path: Path, network):
    result = gtfs_export.build_gtfs(network, tmp_path / "gtfs")
    assert result.id_map_path.is_file()


def test_unknown_service_day_name_is_rejected(tmp_path: Path, network):
    network["service"]["days"] = ["Mon", "tuesday"]
    with pytest.raises(ValueError, match="Mon"):
        gtfs_export.build_gtfs(network, tmp_path / "gtfs")
