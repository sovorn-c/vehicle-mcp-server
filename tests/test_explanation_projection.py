"""Tests for pure deterministic field explanation projection."""

from datetime import UTC, datetime

import pytest

from vehicle_mcp_server.models import (
    CandidateValue,
    ConfidenceAssessment,
    ConfidenceBand,
    ConflictState,
    FieldConflict,
    FieldOutcome,
    ProvenanceLink,
    VehicleRevisionResponse,
)
from vehicle_mcp_server.tools import project_field_explanation


@pytest.fixture
def sample_vehicle() -> VehicleRevisionResponse:
    prov_link = ProvenanceLink(
        observation_id="obs-01",
        source_system="NZTA",
        source_record_id="rec-01",
        retrieved_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        synthetic=True,
    )
    conflict = FieldConflict(
        field_name="ppsr_result",
        conflicting_candidates=[
            CandidateValue(
                field_name="ppsr_result",
                value="NO_MATCH",
                provenance=prov_link,
            ),
            CandidateValue(
                field_name="ppsr_result",
                value="MATCH",
                provenance=prov_link,
            ),
        ],
        state=ConflictState.UNRESOLVED,
        winning_value=None,
        rule_version="conflict-v1",
        rationale="Unresolvable disagreement between sources",
    )
    return VehicleRevisionResponse(
        vin="1HGCR2F85HA000000",
        revision_id="rev-01",
        revision_number=1,
        material_hash="sha256:123456",
        canonical_fields={
            "make": "HONDA",
            "is_commercial": False,
            "stolen_status": "UNKNOWN",
            "odometer": 0,
        },
        field_provenance={"make": [prov_link]},
        conflicts=[conflict],
        confidence=ConfidenceAssessment(
            score=70,
            band=ConfidenceBand.MEDIUM,
            field_scores={"make": 80, "stolen_status": 70},
            field_components={"make": {"authority": 80}},
            rule_version="confidence-v1",
            explanation="Medium confidence",
        ),
        as_of=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        published_at=datetime(2026, 8, 20, 10, 5, tzinfo=UTC),
        synthetic_notice="Demonstration data notice",
    )


def test_project_field_explanation_resolved(sample_vehicle: VehicleRevisionResponse) -> None:
    res = project_field_explanation(sample_vehicle, "make")
    assert res.outcome == FieldOutcome.RESOLVED
    assert res.value == "HONDA"
    assert len(res.provenance) == 1
    assert res.field_confidence_score == 80
    assert res.synthetic_notice == "Demonstration data notice"


def test_project_field_explanation_resolved_falsey_values(
    sample_vehicle: VehicleRevisionResponse,
) -> None:
    # Boolean False
    res_bool = project_field_explanation(sample_vehicle, "is_commercial")
    assert res_bool.outcome == FieldOutcome.RESOLVED
    assert res_bool.value is False

    # Numeric 0
    res_num = project_field_explanation(sample_vehicle, "odometer")
    assert res_num.outcome == FieldOutcome.RESOLVED
    assert res_num.value == 0

    # String UNKNOWN
    res_unk = project_field_explanation(sample_vehicle, "stolen_status")
    assert res_unk.outcome == FieldOutcome.RESOLVED
    assert res_unk.value == "UNKNOWN"


def test_project_field_explanation_unresolved(sample_vehicle: VehicleRevisionResponse) -> None:
    res = project_field_explanation(sample_vehicle, "ppsr_result")
    assert res.outcome == FieldOutcome.UNRESOLVED
    assert res.value is None
    assert len(res.conflicts) == 1
    assert len(res.conflicts[0].conflicting_candidates) == 2
    assert res.rationale == "Unresolvable disagreement between sources"


def test_project_field_explanation_absent(sample_vehicle: VehicleRevisionResponse) -> None:
    res = project_field_explanation(sample_vehicle, "fuel_type")
    assert res.outcome == FieldOutcome.ABSENT
    assert res.value is None
    assert res.available_fields == sorted(
        ["is_commercial", "make", "odometer", "ppsr_result", "stolen_status"]
    )
    assert "fuel_type" in (res.rationale or "")
