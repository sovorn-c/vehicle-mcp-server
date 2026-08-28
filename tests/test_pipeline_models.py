"""Tests for upstream pipeline response models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vehicle_mcp_server.models import (
    CandidateValue,
    ConfidenceAssessment,
    ConfidenceBand,
    ConflictState,
    FieldConflict,
    ProvenanceLink,
    VehicleRevisionResponse,
)


@pytest.fixture
def valid_revision_data() -> dict[str, object]:
    return {
        "vin": "1HGCR2F85HA000000",
        "revision_id": "rev-clean-01",
        "revision_number": 1,
        "material_hash": "sha256:abcd1234abcd1234",
        "canonical_fields": {
            "make": "HONDA",
            "model": "ACCORD",
            "year": 2017,
            "stolen_status": "NOT_LISTED",
            "writeoff_status": "NONE",
            "ppsr_result": "NO_MATCH",
        },
        "field_provenance": {
            "make": [
                {
                    "observation_id": "obs-01",
                    "source_system": "NZTA",
                    "source_record_id": "rec-01",
                    "retrieved_at": "2026-08-20T10:00:00Z",
                    "synthetic": True,
                }
            ]
        },
        "conflicts": [],
        "confidence": {
            "score": 75,
            "band": "MEDIUM",
            "field_scores": {"make": 80, "stolen_status": 75},
            "field_components": {
                "make": {
                    "authority": 80,
                    "agreement": 100,
                    "freshness": 100,
                    "validation": 100,
                }
            },
            "rule_version": "confidence-v1",
            "explanation": "Overall confidence is 75/100 (MEDIUM)",
        },
        "as_of": "2026-08-20T10:00:00Z",
        "published_at": "2026-08-20T10:05:00Z",
        "synthetic_notice": "Demonstration dataset disclaimer",
    }


def test_vehicle_revision_response_valid(valid_revision_data: dict[str, object]) -> None:
    resp = VehicleRevisionResponse.model_validate(valid_revision_data)
    assert resp.vin == "1HGCR2F85HA000000"
    assert resp.revision_number == 1
    assert resp.canonical_fields["make"] == "HONDA"
    assert resp.confidence.score == 75
    assert resp.confidence.band == ConfidenceBand.MEDIUM
    assert resp.synthetic_notice == "Demonstration dataset disclaimer"
    assert resp.as_of == datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)


def test_vehicle_revision_response_rejects_extra_fields(
    valid_revision_data: dict[str, object],
) -> None:
    data = dict(valid_revision_data)
    data["extra_unexpected_field"] = "malicious_or_drifted"
    with pytest.raises(ValidationError):
        VehicleRevisionResponse.model_validate(data)


def test_vehicle_revision_response_with_conflict() -> None:
    conflict_data = {
        "vin": "WAUZZZ8K7BA000000",
        "revision_id": "rev-conflict-01",
        "revision_number": 2,
        "material_hash": "sha256:c0ffee123456",
        "canonical_fields": {
            "make": "AUDI",
            "model": "A4",
        },
        "field_provenance": {},
        "conflicts": [
            {
                "field_name": "ppsr_result",
                "conflicting_candidates": [
                    {
                        "field_name": "ppsr_result",
                        "value": "NO_MATCH",
                        "provenance": {
                            "observation_id": "obs-02",
                            "source_system": "PPSR",
                            "source_record_id": "ppsr-01",
                            "retrieved_at": "2026-08-20T10:00:00Z",
                            "synthetic": True,
                        },
                    },
                    {
                        "field_name": "ppsr_result",
                        "value": "MATCH",
                        "provenance": {
                            "observation_id": "obs-03",
                            "source_system": "DEALER",
                            "source_record_id": "dlr-01",
                            "retrieved_at": "2026-08-20T11:00:00Z",
                            "synthetic": True,
                        },
                    },
                ],
                "state": "UNRESOLVED",
                "winning_value": None,
                "rule_version": "conflict-v1",
                "rationale": "Equal authority disagreement",
            }
        ],
        "confidence": {
            "score": 40,
            "band": "LOW",
            "field_scores": {"ppsr_result": 0},
            "field_components": {},
            "rule_version": "confidence-v1",
            "explanation": "Low confidence due to unresolved conflict",
        },
        "as_of": "2026-08-20T12:00:00Z",
        "published_at": "2026-08-20T12:05:00Z",
    }
    resp = VehicleRevisionResponse.model_validate(conflict_data)
    assert "ppsr_result" not in resp.canonical_fields
    assert len(resp.conflicts) == 1
    assert resp.conflicts[0].state == ConflictState.UNRESOLVED
    assert len(resp.conflicts[0].conflicting_candidates) == 2


def test_vehicle_revision_response_is_immutable(
    valid_revision_data: dict[str, object],
) -> None:
    resp = VehicleRevisionResponse.model_validate(valid_revision_data)
    with pytest.raises((ValidationError, TypeError)):
        resp.revision_number = 2  # type: ignore[misc]
