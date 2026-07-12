"""
Integration test for GET /samples/{name}/predict.

We seed abundance rows directly in the DB (skipping the whole Snakemake
pipeline), then hit the endpoint and verify the ML wrapper is called and
the response is well-formed. The sklearn pipeline is mocked in
conftest.py's `mock_ml_pipeline` fixture.
"""

from __future__ import annotations

import pytest

from src.backend.models import Abundance


async def _seed_species_abundance(db_session, sample):
    """Insert three abundance rows for the fixture sample."""
    rows = [
        Abundance(
            sample_id=sample.id,
            sample_name=sample.sample_name,
            classifier="kraken2+bracken",
            clade=clade,
            taxa_id=t_id,
            rank="species",
            relative_abundance=abund,
        )
        for clade, t_id, abund in [
            ("Bacteroides", 817, 0.4),
            ("Prevotella", 165179, 0.3),
            ("Faecalibacterium", 853, 0.3),
        ]
    ]
    db_session.add_all(rows)
    await db_session.commit()


class TestPredictEndpoint:

    async def test_returns_lat_lon_for_valid_sample(
        self, api_client, db_session, created_sample, mock_ml_pipeline
    ):
        await _seed_species_abundance(db_session, created_sample)

        response = await api_client.get(f"/samples/{created_sample.sample_name}/predict")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["sample_name"] == created_sample.sample_name
        assert 55.0 < body["latitude"] < 56.0
        assert 12.0 < body["longitude"] < 14.0

    async def test_returns_404_when_no_abundance(
        self, api_client, created_sample, mock_ml_pipeline
    ):
        # Sample exists but has no abundance rows yet.
        response = await api_client.get(f"/samples/{created_sample.sample_name}/predict")
        assert response.status_code == 404
        assert "No abundance data" in response.json()["detail"] or \
               "Has the pipeline completed" in response.json()["detail"]

    async def test_returns_404_when_sample_missing(self, api_client, mock_ml_pipeline):
        response = await api_client.get("/samples/no_such_sample/predict")
        assert response.status_code == 404

    async def test_returns_500_when_model_crashes(
        self, api_client, db_session, created_sample, mock_ml_pipeline
    ):
        await _seed_species_abundance(db_session, created_sample)
        # Force the mocked pipeline to blow up.
        mock_ml_pipeline.predict.side_effect = RuntimeError("model exploded")

        response = await api_client.get(f"/samples/{created_sample.sample_name}/predict")
        assert response.status_code == 500
        assert "model exploded" in response.json()["detail"]
