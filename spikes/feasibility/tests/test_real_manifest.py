from taxigraph_spike import real_manifest


def test_blank_manifest_is_data_blocked():
    validation = real_manifest.validate_real_manifest({})
    assert validation.status == "data_blocked"
    assert "source_rights_reference" in validation.missing


def test_blank_template_is_also_data_blocked():
    template = real_manifest.blank_manifest_template()
    validation = real_manifest.validate_real_manifest(template)
    assert validation.status == "data_blocked"


def _complete_manifest():
    variant = {
        "route_id": "R1",
        "direction": "north_to_south",
        "ordered_boarding_points": ["A", "B"],
        "reviewer": "local verifier",
        "observation_date": "2026-09-01",
    }

    def case(kind: str, index: int):
        return {
            "case_id": f"case-{index}",
            "kind": kind,
            "origin": "A",
            "destination": "B",
            "expected_result": "journey_found",
            "reviewer": "local verifier",
            "observation_date": "2026-09-01",
        }

    negative_kinds = list(real_manifest.REQUIRED_NEGATIVE_CASE_KINDS)
    cases = [case("direct", i) for i in range(8)]
    cases += [case(kind, 8 + i) for i, kind in enumerate(negative_kinds)]

    return {
        "source_rights_reference": "City of Cape Town written permission ref #123, 2026-08-01",
        "verified_corridor": "Bellville corridor",
        "directed_variants": [variant, variant, variant],
        "boarding_evidence": "field observation log",
        "service_window_evidence": "field observation log",
        "headway_timing_evidence": "field observation log",
        "dataset_version": "2026-09-01",
        "evaluation_cases": cases,
    }


def test_complete_manifest_is_eligible():
    validation = real_manifest.validate_real_manifest(_complete_manifest())
    assert validation.status == "eligible", validation.missing


def test_public_url_alone_is_rejected_as_rights():
    manifest = _complete_manifest()
    manifest["source_rights_reference"] = "public URL"
    validation = real_manifest.validate_real_manifest(manifest)
    assert validation.status == "data_blocked"
    assert any("not a licence" in m for m in validation.missing)


def test_too_few_evaluation_cases():
    manifest = _complete_manifest()
    manifest["evaluation_cases"] = manifest["evaluation_cases"][:5]
    validation = real_manifest.validate_real_manifest(manifest)
    assert validation.status == "data_blocked"
    assert any("evaluation_cases" in m for m in validation.missing)


def test_non_object_manifest_is_data_blocked():
    for bad in ([], "text", None, 3):
        validation = real_manifest.validate_real_manifest(bad)
        assert validation.status == "data_blocked"


def test_non_object_entries_are_reported_not_raised():
    manifest = _complete_manifest()
    manifest["directed_variants"][0] = "R1"
    manifest["evaluation_cases"][0] = None
    validation = real_manifest.validate_real_manifest(manifest)
    assert validation.status == "data_blocked"
    assert "directed_variants[0]: must be an object" in validation.missing
    assert "evaluation_cases[0]: must be an object" in validation.missing


def test_non_list_fields_are_reported_not_raised():
    manifest = _complete_manifest()
    manifest["directed_variants"] = "three variants"
    validation = real_manifest.validate_real_manifest(manifest)
    assert "directed_variants: must be a list" in validation.missing
