"""Tests for catalog discovery models: ListVehiclesInput, VehicleSummary, VehicleCatalogPage."""

import pytest
from pydantic import ValidationError

from vehicle_mcp_server.models import (
    ListVehiclesInput,
    VehicleCatalogPage,
    VehicleSummary,
)


def test_list_vehicles_input_defaults() -> None:
    inp = ListVehiclesInput()
    assert inp.limit == 20
    assert inp.offset == 0


def test_list_vehicles_input_custom_valid() -> None:
    inp = ListVehiclesInput(limit=50, offset=10)
    assert inp.limit == 50
    assert inp.offset == 10


def test_list_vehicles_input_boundaries() -> None:
    assert ListVehiclesInput(limit=1, offset=0).limit == 1
    assert ListVehiclesInput(limit=100, offset=0).limit == 100


@pytest.mark.parametrize(
    "invalid_kwargs",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": -1},
        {"offset": -1},
        {"limit": "20"},  # Rejects string coercion
        {"limit": 10.5},  # Rejects float
        {"limit": True},  # Rejects bool
        {"offset": False},  # Rejects bool
        {"unknown_field": "val"},  # Rejects extra fields
    ],
)
def test_list_vehicles_input_rejections(invalid_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ListVehiclesInput(**invalid_kwargs)


def test_list_vehicles_input_frozen() -> None:
    inp = ListVehiclesInput()
    with pytest.raises(ValidationError):
        inp.limit = 10  # type: ignore[misc]


def test_vehicle_summary_valid() -> None:
    summary = VehicleSummary(
        vin="1HGCR2F85HA000000",
        make="HONDA",
        model="ACCORD",
        year=2017,
        registration_status="CURRENT",
        confidence_score=0.85,
        has_conflicts=False,
        revision_number=2,
        synthetic=True,
    )
    assert summary.vin == "1HGCR2F85HA000000"
    assert summary.make == "HONDA"
    assert summary.confidence_score == 0.85
    assert summary.revision_number == 2
    assert summary.synthetic is True


def test_vehicle_summary_nullable_fields() -> None:
    summary = VehicleSummary(
        vin="1HGCR2F85HA000000",
        make=None,
        model=None,
        year=None,
        registration_status=None,
        confidence_score=None,
        has_conflicts=False,
        revision_number=1,
        synthetic=False,
    )
    assert summary.make is None
    assert summary.model is None
    assert summary.year is None
    assert summary.registration_status is None
    assert summary.confidence_score is None
    assert summary.has_conflicts is False
    assert summary.synthetic is False


@pytest.mark.parametrize(
    "invalid_kwargs",
    [
        {"vin": "SHORT"},
        {"vin": "1HGCR2F85HA000000", "confidence_score": float("nan")},
        {"vin": "1HGCR2F85HA000000", "confidence_score": float("inf")},
        {"vin": "1HGCR2F85HA000000", "extra": "invalid"},
        # Strict mode: string year rejected
        {
            "vin": "1HGCR2F85HA000000",
            "make": "HONDA",
            "model": "ACCORD",
            "year": "2017",
            "registration_status": "CURRENT",
            "confidence_score": 0.85,
            "has_conflicts": False,
            "revision_number": 1,
            "synthetic": False,
        },
        # Missing required summary fields (even nullable ones must not be omitted from wire schema)
        {
            "vin": "1HGCR2F85HA000000",
            "model": "ACCORD",
            "year": 2017,
            "registration_status": "CURRENT",
            "confidence_score": 0.85,
            "has_conflicts": False,
            "revision_number": 1,
            "synthetic": False,
        },
        {"vin": "1HGCR2F85HA000000", "revision_number": 1, "synthetic": False},
        {"vin": "1HGCR2F85HA000000", "has_conflicts": False, "synthetic": False},
        {"vin": "1HGCR2F85HA000000", "has_conflicts": False, "revision_number": 1},
        # Reject un-normalized VINs from upstream (lowercase or whitespace-padded)
        {
            "vin": "1hgcr2f85ha000000",
            "make": "HONDA",
            "model": "ACCORD",
            "year": 2017,
            "registration_status": "CURRENT",
            "confidence_score": 0.85,
            "has_conflicts": False,
            "revision_number": 1,
            "synthetic": False,
        },
        {
            "vin": " 1HGCR2F85HA000000 ",
            "make": "HONDA",
            "model": "ACCORD",
            "year": 2017,
            "registration_status": "CURRENT",
            "confidence_score": 0.85,
            "has_conflicts": False,
            "revision_number": 1,
            "synthetic": False,
        },
    ],
)
def test_vehicle_summary_rejections(invalid_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        VehicleSummary(**invalid_kwargs)  # type: ignore[arg-type]


def test_vehicle_catalog_page_valid() -> None:
    item = VehicleSummary(
        vin="1HGCR2F85HA000000",
        make="HONDA",
        model=None,
        year=None,
        registration_status=None,
        confidence_score=None,
        has_conflicts=False,
        revision_number=1,
        synthetic=False,
    )
    page = VehicleCatalogPage(
        items=[item],
        total=1,
        limit=20,
        offset=0,
        disclaimer="Synthetic data limitation notice",
    )
    assert len(page.items) == 1
    assert page.total == 1
    assert page.limit == 20
    assert page.offset == 0
    assert page.disclaimer == "Synthetic data limitation notice"


def test_vehicle_catalog_page_empty_valid() -> None:
    page = VehicleCatalogPage(
        items=[],
        total=0,
        limit=20,
        offset=0,
    )
    assert len(page.items) == 0
    assert page.total == 0
    assert page.disclaimer is None


@pytest.mark.parametrize(
    "invalid_kwargs",
    [
        {"items": [], "total": -1, "limit": 20, "offset": 0},
        {"items": [], "total": 0, "limit": 0, "offset": 0},
        {"items": [], "total": 0, "limit": 101, "offset": 0},
        {"items": [], "total": 0, "limit": 20, "offset": -1},
        {"items": [], "total": 0, "limit": 20, "offset": 0, "extra": "nope"},
    ],
)
def test_vehicle_catalog_page_rejections(invalid_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        VehicleCatalogPage(**invalid_kwargs)  # type: ignore[arg-type]
