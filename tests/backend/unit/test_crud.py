"""
Unit tests for `backend/crud.py`.

We use a REAL (in-memory) SQLite database via the `db_session` fixture.
That fixture guarantees the DB is empty at the start of every test and
disposed of at the end. There is no HTTP layer here — we call the CRUD
functions directly.

Some people call this an "integration test with the DB". In this codebase
we treat it as a unit test for the CRUD layer, because the DB is a fake
substitute for the real Postgres/SQLite production DB and no other
component is involved.
"""

from __future__ import annotations

import pytest

from src.backend import crud
from src.backend.models import Abundance



# create_sample

class TestCreateSample:

    async def test_persists_new_row(self, db_session):
        sample = await crud.create_sample(
            db=db_session,
            username="alice",
            email="alice@example.com",
            sample_name="malmo_01",
            r1_path="/tmp/r1.fq.gz",
            r2_path="/tmp/r2.fq.gz",
        )
        # 1. Auto-generated fields must be populated after commit+refresh.
        assert sample.id is not None
        assert sample.submitted_at is not None
        # 2. Default status must be 'pending'.
        assert sample.status == "pending"
        # 3. User-supplied fields round-trip correctly.
        assert sample.sample_name == "malmo_01"
        assert sample.r1_path == "/tmp/r1.fq.gz"



# get_sample_by_name / by_id

class TestGetSample:

    async def test_by_name_returns_row_when_present(self, db_session, created_sample):
        found = await crud.get_sample_by_name(db_session, created_sample.sample_name)
        assert found is not None
        assert found.id == created_sample.id

    async def test_by_name_returns_none_when_missing(self, db_session):
        found = await crud.get_sample_by_name(db_session, "does_not_exist")
        assert found is None

    async def test_by_id_returns_row_when_present(self, db_session, created_sample):
        found = await crud.get_sample_by_id(db_session, created_sample.id)
        assert found is not None
        assert found.sample_name == created_sample.sample_name



# get_all_samples

async def test_get_all_samples_empty(db_session):
    assert await crud.get_all_samples(db_session) == []


async def test_get_all_samples_orders_newest_first(db_session):
    for i in range(3):
        await crud.create_sample(
            db=db_session,
            username="u",
            email="u@e.c",
            sample_name=f"s_{i}",
            r1_path="/tmp/r1",
            r2_path="/tmp/r2",
        )
    rows = await crud.get_all_samples(db_session)
    assert len(rows) == 3
    # Latest insert should be first (order_by submitted_at desc).
    assert rows[0].sample_name == "s_2"



# update_sample_status

class TestUpdateStatus:

    async def test_updates_status_field(self, db_session, created_sample):
        updated = await crud.update_sample_status(db_session, created_sample.id, "processing")
        assert updated.status == "processing"

    async def test_updates_extra_kwargs(self, db_session, created_sample):
        updated = await crud.update_sample_status(
            db_session, created_sample.id, "failed", error_msg="pipeline crashed"
        )
        assert updated.status == "failed"
        assert updated.error_msg == "pipeline crashed"

    async def test_ignores_unknown_attrs(self, db_session, created_sample):
        # `nonsense` is not a column — should be silently ignored, not raise.
        updated = await crud.update_sample_status(
            db_session, created_sample.id, "processing", nonsense="oops"
        )
        assert updated.status == "processing"
        assert not hasattr(updated, "nonsense")

    async def test_returns_none_for_missing_sample(self, db_session):
        result = await crud.update_sample_status(db_session, "no-such-id", "processing")
        assert result is None



# delete_sample

class TestDeleteSample:

    async def test_returns_true_when_deleted(self, db_session, created_sample):
        assert await crud.delete_sample(db_session, created_sample.sample_name) is True
        assert await crud.get_sample_by_name(db_session, created_sample.sample_name) is None

    async def test_returns_false_when_missing(self, db_session):
        assert await crud.delete_sample(db_session, "does_not_exist") is False



# update_celery_task_id

async def test_update_celery_task_id(db_session, created_sample):
    updated = await crud.update_celery_task_id(db_session, created_sample.id, "task-42")
    assert updated.celery_task_id == "task-42"



# fetch_abundance — returns a wide-form pandas DataFrame

class TestFetchAbundance:

    async def _seed_abundance(self, db_session, sample_id, sample_name):
        rows = [
            Abundance(
                sample_id=sample_id,
                sample_name=sample_name,
                classifier="kraken2+bracken",
                clade=clade,
                taxa_id=taxa_id,
                rank="species",
                relative_abundance=abundance,
            )
            for clade, taxa_id, abundance in [
                ("Bacteroides fragilis", 817, 0.15),
                ("Prevotella copri", 165179, 0.08),
                ("Faecalibacterium prausnitzii", 853, 0.20),
            ]
        ]
        db_session.add_all(rows)
        await db_session.commit()

    async def test_returns_wide_dataframe(self, db_session, created_sample):
        await self._seed_abundance(db_session, created_sample.id, created_sample.sample_name)

        df = await crud.fetch_abundance(db_session, created_sample.sample_name, "species")
        # Wide format: 1 row, 3 columns (one per clade).
        assert df.shape == (1, 3)
        assert "Bacteroides fragilis" in df.columns
        assert df["Bacteroides fragilis"].iloc[0] == pytest.approx(0.15)

    async def test_raises_when_no_data(self, db_session, created_sample):
        with pytest.raises(ValueError, match="No abundance data found"):
            await crud.fetch_abundance(db_session, created_sample.sample_name, "species")
