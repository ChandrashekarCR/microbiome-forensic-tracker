"""
Unit tests for `backend/schemas.py`.

These are pure Pydantic tests — no DB, no HTTP, no filesystem.
These tests do only one thing check the schemas, i.e how the input should be recieved from the user
and how the output is to be given to the user.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.backend.schemas import (
    AbundanceResponse,
    DeleteResponse,
    PredictionResponse,
    SampleCreate,
    SampleResponse,
)


# SampleCreate — the input schema for POST /samples
class TestSampleCreate:
    """Group related tests in a class so the report is easier to read."""

    def test_accepts_valid_payload(self):
        obj = SampleCreate(
            username="alice",
            email="alice@example.com",
            sample_name="malmo_01",
        )
        assert obj.username == "alice"
        assert obj.email == "alice@example.com"
        assert obj.sample_name == "malmo_01"

    def test_rejects_missing_field(self):
        # Pydantic must raise ValidationError when a required field is absent.
        with pytest.raises(ValidationError) as exc_info:
            SampleCreate(username="alice", email="a@b.c")  # sample_name missing

        # Sanity-check that the error mentions the missing field, not just
        # "something went wrong".
        assert "sample_name" in str(exc_info.value)

    def test_rejects_wrong_type(self):
        with pytest.raises(ValidationError):
            SampleCreate(username=123, email="a@b.c", sample_name="x")  # username is int


# SampleResponse — the output schema for GET /samples/{name}
class TestSampleResponse:
    def test_serialises_minimum_fields(self):
        obj = SampleResponse(
            id=uuid.uuid4(),
            sample_name="malmo_01",
            username="alice",
            email="alice@example.com",
            status="pending",
            submitted_at=datetime.utcnow(),
        )
        # Optional fields default to None.
        assert obj.started_at is None
        assert obj.completed_at is None
        assert obj.error_msg is None

    def test_accepts_full_fields(self):
        now = datetime.utcnow()
        obj = SampleResponse(
            id=uuid.uuid4(),
            sample_name="malmo_01",
            username="alice",
            email="alice@example.com",
            status="completed",
            submitted_at=now,
            started_at=now,
            completed_at=now,
            error_msg=None,
        )
        assert obj.status == "completed"

    def test_from_orm_compatible(self):
        """Verify `from_attributes = True` lets us build from an object with attrs."""

        class FakeOrm:
            id = uuid.uuid4()
            sample_name = "malmo_01"
            username = "alice"
            email = "alice@example.com"
            status = "pending"
            submitted_at = datetime.utcnow()
            started_at = None
            completed_at = None
            error_msg = None

        obj = SampleResponse.model_validate(FakeOrm())
        assert obj.sample_name == "malmo_01"


# AbundanceResponse
def test_abundance_response_types():
    obj = AbundanceResponse(
        sample_id="abc",
        sample_name="malmo_01",
        classifier="kraken2+bracken",
        clade="Bacteroides fragilis",
        taxa_id=817,
        rank="species",
        relative_abundance=0.15,
    )
    assert isinstance(obj.taxa_id, int)
    assert isinstance(obj.relative_abundance, float)


def test_abundance_rejects_non_numeric_abundance():
    with pytest.raises(ValidationError):
        AbundanceResponse(
            sample_id="abc",
            sample_name="malmo_01",
            classifier="k",
            clade="c",
            taxa_id=1,
            rank="species",
            relative_abundance="not-a-number",
        )


# PredictionResponse & DeleteResponse — smoke tests
def test_prediction_response_shape():
    obj = PredictionResponse(sample_name="malmo_01", latitude=55.6, longitude=13.0)
    assert (obj.latitude, obj.longitude) == (55.6, 13.0)


def test_delete_response_shape():
    obj = DeleteResponse(ok=True, message="deleted")
    assert obj.ok is True
    assert "deleted" in obj.message


# Parametrized tests — the same logic, many inputs, one test function.
@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {},  # everything missing
        {"username": "a"},  # missing email + sample_name
        {"username": "a", "email": "a@b.c"},  # missing sample_name
    ],
)
def test_sample_create_requires_all_fields(bad_kwargs):
    with pytest.raises(ValidationError):
        SampleCreate(**bad_kwargs)
