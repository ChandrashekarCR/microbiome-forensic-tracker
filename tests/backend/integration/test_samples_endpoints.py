"""
Integration tests for the /samples routes.

These exercise the full FastAPI stack:
    HTTP request  →  Pydantic validation
                  →  crud.py
                  →  SQLAlchemy (in-memory SQLite)
                  →  Pydantic response model  →  HTTP response

Celery, filesystem and the ML model are all mocked (see conftest.py).
"""

from __future__ import annotations

import pytest

# POST /samples


class TestUploadSample:
    async def test_creates_sample_returns_201(self, api_client, sample_payload, fake_fastq_files, temp_upload_dir, mock_celery):
        response = await api_client.post(
            "/samples",
            data=sample_payload,
            files={"r1": fake_fastq_files["r1"], "r2": fake_fastq_files["r2"]},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["sample_name"] == sample_payload["sample_name"]
        assert body["status"] == "pending"
        assert body["username"] == "alice"

        # Uploaded files landed on disk in the temp folder.
        assert (temp_upload_dir / "malmo_park_01_R1.fastq.gz").exists()
        assert (temp_upload_dir / "malmo_park_01_R2.fastq.gz").exists()

        # Celery task was scheduled exactly once.
        assert mock_celery.call_count == 1

    async def test_duplicate_sample_name_returns_400(self, api_client, sample_payload, fake_fastq_files, temp_upload_dir, created_sample):
        # `created_sample` fixture already inserted a row with this name.
        response = await api_client.post(
            "/samples",
            data=sample_payload,
            files={"r1": fake_fastq_files["r1"], "r2": fake_fastq_files["r2"]},
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.parametrize(
        "bad_filename",
        ["reads.txt", "reads.fastq", "reads.fq", "reads.bam"],
    )
    async def test_rejects_wrong_file_extension(self, api_client, sample_payload, fake_fastq_files, temp_upload_dir, bad_filename):
        import io

        bad = (bad_filename, io.BytesIO(b"data"), "application/octet-stream")
        response = await api_client.post(
            "/samples",
            data=sample_payload,
            files={"r1": bad, "r2": fake_fastq_files["r2"]},
        )
        assert response.status_code == 400
        assert ".fastq.gz" in response.json()["detail"] or ".fq.gz" in response.json()["detail"]

    async def test_missing_form_field_returns_422(self, api_client, fake_fastq_files, temp_upload_dir):
        # No 'username' field — FastAPI/Pydantic must reject with 422.
        response = await api_client.post(
            "/samples",
            data={"email": "a@b.c", "sample_name": "x"},
            files={"r1": fake_fastq_files["r1"], "r2": fake_fastq_files["r2"]},
        )
        assert response.status_code == 422


# GET /samples


class TestListSamples:
    async def test_empty_list(self, api_client):
        response = await api_client.get("/samples")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["samples"] == []

    async def test_lists_existing_samples(self, api_client, created_sample):
        response = await api_client.get("/samples")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["samples"][0]["sample_name"] == created_sample.sample_name


# GET /samples/{name}


class TestGetSampleStatus:
    async def test_returns_existing_sample(self, api_client, created_sample):
        response = await api_client.get(f"/samples/{created_sample.sample_name}")
        assert response.status_code == 201
        assert response.json()["sample_name"] == created_sample.sample_name

    async def test_returns_400_for_missing_sample(self, api_client):
        response = await api_client.get("/samples/does_not_exist")
        assert response.status_code == 400
        assert response.json()["detail"] == "Sample not found"


# DELETE /samples/{name}


class TestDeleteSample:
    async def test_deletes_existing_sample(self, api_client, created_sample):
        response = await api_client.delete(f"/samples/{created_sample.sample_name}")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert created_sample.sample_name in body["message"]

        # Follow-up GET must now return 400.
        followup = await api_client.get(f"/samples/{created_sample.sample_name}")
        assert followup.status_code == 400

    async def test_returns_404_when_missing(self, api_client):
        response = await api_client.delete("/samples/does_not_exist")
        assert response.status_code == 404
