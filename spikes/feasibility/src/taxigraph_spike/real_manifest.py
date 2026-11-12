"""Minimal contract a real-mode manifest must satisfy before any real export.

This is a fail-closed gate, not a data importer. An empty or partially
filled manifest must come back `data_blocked` and name exactly what is
missing; it must never fall back to a plausible-looking feed.

See docs/MVP-SPEC.md (12-case corpus) and docs/SOL-HANDOFF.md (evidence
request template) for what each field represents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MIN_EVALUATION_CASES = 12
REQUIRED_NEGATIVE_CASE_KINDS = {
    "unsupported_reverse_direction",
    "false_transfer_across_barrier",
    "outside_verified_service_window",
    "outside_coverage",
}

REQUIRED_TOP_LEVEL_FIELDS = (
    "source_rights_reference",
    "verified_corridor",
    "directed_variants",
    "boarding_evidence",
    "service_window_evidence",
    "headway_timing_evidence",
    "dataset_version",
    "evaluation_cases",
)

REQUIRED_VARIANT_FIELDS = (
    "route_id",
    "direction",
    "ordered_boarding_points",
    "reviewer",
    "observation_date",
)

REQUIRED_EVALUATION_CASE_FIELDS = (
    "case_id",
    "kind",
    "origin",
    "destination",
    "expected_result",
    "reviewer",
    "observation_date",
)


@dataclass(frozen=True)
class ManifestValidation:
    status: str  # "eligible" or "data_blocked"
    missing: list[str] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return self.status == "eligible"


def _require(container: dict[str, Any], fields: tuple[str, ...], prefix: str, missing: list[str]) -> None:
    for name in fields:
        value = container.get(name)
        if value in (None, "", [], {}):
            missing.append(f"{prefix}{name}")


def _object_entries(manifest: dict[str, Any], key: str, missing: list[str]) -> list[tuple[int, dict[str, Any]]]:
    """Return (index, object) pairs for a list field; anything else is recorded as missing."""

    value = manifest.get(key) or []
    if not isinstance(value, list):
        missing.append(f"{key}: must be a list")
        return []
    entries = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            entries.append((index, item))
        else:
            missing.append(f"{key}[{index}]: must be an object")
    return entries


def validate_real_manifest(manifest: Any) -> ManifestValidation:
    if not isinstance(manifest, dict):
        return ManifestValidation(status="data_blocked", missing=["manifest: must be a JSON object"])

    missing: list[str] = []
    _require(manifest, REQUIRED_TOP_LEVEL_FIELDS, "", missing)

    variants = _object_entries(manifest, "directed_variants", missing)
    if not (3 <= len(variants) <= 5):
        missing.append(f"directed_variants: need 3-5, got {len(variants)}")
    for index, variant in variants:
        _require(variant, REQUIRED_VARIANT_FIELDS, f"directed_variants[{index}].", missing)

    cases = _object_entries(manifest, "evaluation_cases", missing)
    if len(cases) < MIN_EVALUATION_CASES:
        missing.append(f"evaluation_cases: need >= {MIN_EVALUATION_CASES}, got {len(cases)}")
    present_negative_kinds = set()
    for index, case in cases:
        _require(case, REQUIRED_EVALUATION_CASE_FIELDS, f"evaluation_cases[{index}].", missing)
        kind = case.get("kind")
        if kind in REQUIRED_NEGATIVE_CASE_KINDS:
            present_negative_kinds.add(kind)

    missing_negative_kinds = REQUIRED_NEGATIVE_CASE_KINDS - present_negative_kinds
    if missing_negative_kinds:
        missing.append(f"evaluation_cases: missing negative kinds {sorted(missing_negative_kinds)}")

    # Repeating one case must not pad the corpus up to the required size.
    case_ids = [c["case_id"] for _, c in cases if isinstance(c.get("case_id"), str)]
    duplicate_ids = sorted({i for i in case_ids if case_ids.count(i) > 1})
    if duplicate_ids:
        missing.append(f"evaluation_cases: duplicate case_id {duplicate_ids}")

    rights = manifest.get("source_rights_reference")
    if isinstance(rights, str) and rights.strip().lower() in {"public url", "public portal", "todo"}:
        missing.append(
            "source_rights_reference: a public URL alone is not a licence; "
            "record the actual permission scope"
        )

    if missing:
        return ManifestValidation(status="data_blocked", missing=missing)
    return ManifestValidation(status="eligible", missing=[])


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def blank_manifest_template() -> dict[str, Any]:
    """Compact blank record maintainers can fill in; unknown fields may stay null."""

    return {
        "source_rights_reference": None,
        "verified_corridor": None,
        "dataset_version": None,
        "directed_variants": [
            {
                "route_id": None,
                "direction": None,
                "ordered_boarding_points": None,
                "recurring_days_hours": None,
                "reviewer": None,
                "observation_date": None,
            }
        ],
        "boarding_evidence": None,
        "service_window_evidence": None,
        "headway_timing_evidence": None,
        "evaluation_cases": [
            {
                "case_id": None,
                "kind": None,
                "origin": None,
                "destination": None,
                "service_datetime": None,
                "expected_route_boarding_transfer_sequence": None,
                "expected_result": None,
                "observation_context": None,
                "reviewer": None,
                "observation_date": None,
            }
        ],
    }
