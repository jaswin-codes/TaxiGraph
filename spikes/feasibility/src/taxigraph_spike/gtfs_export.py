"""Narrow, auditable projection from a canonical network dict to GTFS.

Every value written here must trace back to a fixture field or a documented
derivation (e.g. "00:00:00 + stop_offsets_seconds"). No fare tables are
written because fares are unknown for the synthetic fixture and must stay
unknown, never zero, for any future real record. Uses only the standard
library csv/zipfile; this is a fixed set of GTFS tables, not a generic
parser.
"""

from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GTFS_TABLES = (
    "agency.txt",
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "frequencies.txt",
    "calendar.txt",
    "feed_info.txt",
)

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
ROUTE_TYPE_TAXI_PROXY = 3  # GTFS route_type 3 = bus; no dedicated informal-taxi type exists.
FEED_ID = "SYN"  # Explicit rather than relying on OTP's positional default ("1").


@dataclass(frozen=True)
class GtfsExportResult:
    out_dir: Path
    zip_path: Path
    id_map_path: Path
    warnings: list[str] = field(default_factory=list)


def _seconds_to_gtfs_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_gtfs(network: dict[str, Any], out_dir: Path) -> GtfsExportResult:
    if network.get("provenance", {}).get("kind") != "synthetic":
        raise ValueError("gtfs_export currently only projects the synthetic fixture shape; see module docstring")

    out_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    id_map: dict[str, dict[str, str]] = {"stops": {}, "routes": {}, "trips": {}}

    agency = network["agency"]
    _write_csv(
        out_dir / "agency.txt",
        ["agency_id", "agency_name", "agency_url", "agency_timezone"],
        [
            {
                "agency_id": agency["agency_id"],
                "agency_name": agency["agency_name"],
                "agency_url": agency["agency_url"],
                "agency_timezone": agency["agency_timezone"],
            }
        ],
    )

    stop_rows = []
    for stop in network["stops"]:
        id_map["stops"][stop["stop_id"]] = stop["stop_id"]
        stop_rows.append(
            {
                "stop_id": stop["stop_id"],
                "stop_name": stop["stop_name"],
                "stop_lat": stop["lat"],
                "stop_lon": stop["lon"],
            }
        )
    _write_csv(out_dir / "stops.txt", ["stop_id", "stop_name", "stop_lat", "stop_lon"], stop_rows)

    route_rows = []
    for route in network["routes"]:
        id_map["routes"][route["route_id"]] = route["route_id"]
        route_rows.append(
            {
                "route_id": route["route_id"],
                "agency_id": agency["agency_id"],
                "route_short_name": route["route_short_name"],
                "route_long_name": route["route_long_name"],
                "route_type": route.get("route_type", ROUTE_TYPE_TAXI_PROXY),
            }
        )
    _write_csv(
        out_dir / "routes.txt",
        ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
        route_rows,
    )

    service = network["service"]
    unknown_days = set(service["days"]) - set(WEEKDAYS)
    if unknown_days:
        raise ValueError(f"service days must be lowercase weekday names, got {sorted(unknown_days)}")
    day_flags = {day: ("1" if day in service["days"] else "0") for day in WEEKDAYS}
    _write_csv(
        out_dir / "calendar.txt",
        ["service_id", *day_flags.keys(), "start_date", "end_date"],
        [
            {
                "service_id": service["service_id"],
                **day_flags,
                "start_date": service["start_date"],
                "end_date": service["end_date"],
            }
        ],
    )

    trip_rows = []
    stop_time_rows = []
    frequency_rows = []
    for trip in network["trips"]:
        id_map["trips"][trip["trip_id"]] = trip["trip_id"]
        trip_rows.append(
            {
                "trip_id": trip["trip_id"],
                "route_id": trip["route_id"],
                "service_id": service["service_id"],
                "direction_id": trip["direction_id"],
            }
        )

        stops = trip["stops"]
        offsets = trip["stop_offsets_seconds"]
        if len(stops) != len(offsets):
            raise ValueError(f"trip {trip['trip_id']}: stops/offsets length mismatch")

        for sequence, (stop_id, offset) in enumerate(zip(stops, offsets), start=1):
            gtfs_time = _seconds_to_gtfs_time(offset)
            stop_time_rows.append(
                {
                    "trip_id": trip["trip_id"],
                    "arrival_time": gtfs_time,
                    "departure_time": gtfs_time,
                    "stop_id": stop_id,
                    "stop_sequence": sequence,
                }
            )

        exact_times = trip.get("exact_times", 0)
        if exact_times != 0:
            warnings.append(
                f"trip {trip['trip_id']}: exact_times={exact_times} requested; "
                "spike policy is exact_times=0 for any non-exact profile"
            )
        frequency_rows.append(
            {
                "trip_id": trip["trip_id"],
                "start_time": trip["headway_start"],
                "end_time": trip["headway_end"],
                "headway_secs": trip["headway_seconds"],
                "exact_times": 0,
            }
        )

    _write_csv(
        out_dir / "trips.txt",
        ["trip_id", "route_id", "service_id", "direction_id"],
        trip_rows,
    )
    _write_csv(
        out_dir / "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        stop_time_rows,
    )
    _write_csv(
        out_dir / "frequencies.txt",
        ["trip_id", "start_time", "end_time", "headway_secs", "exact_times"],
        frequency_rows,
    )

    _write_csv(
        out_dir / "feed_info.txt",
        [
            "feed_publisher_name",
            "feed_publisher_url",
            "feed_lang",
            "feed_version",
            "feed_start_date",
            "feed_end_date",
            "feed_id",
        ],
        [
            {
                "feed_publisher_name": "TaxiGraph feasibility spike (synthetic)",
                "feed_publisher_url": agency["agency_url"],
                "feed_lang": "en",
                "feed_version": network["provenance"]["created"],
                "feed_start_date": service["start_date"],
                "feed_end_date": service["end_date"],
                "feed_id": FEED_ID,
            }
        ],
    )

    # No fare_attributes.txt / fare_rules.txt: fares are unknown for this fixture
    # and must never be exported as zero or invented.

    id_map_path = out_dir / "id-map.json"
    with id_map_path.open("w", encoding="utf-8") as handle:
        json.dump(id_map, handle, indent=2, sort_keys=True)

    zip_path = out_dir / "feed.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in GTFS_TABLES:
            archive.write(out_dir / table, arcname=table)

    return GtfsExportResult(out_dir=out_dir, zip_path=zip_path, id_map_path=id_map_path, warnings=warnings)
