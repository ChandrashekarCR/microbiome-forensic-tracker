"""
Global test fixtures. Anything defined here is automatically available to
every test in this folder (and subfolders) without importing.

Why fixtures?
-------------
A fixture is a *reusable, declarative* piece of test setup.  Instead of
writing 6 lines of "create a fresh DB session" at the top of every test,
you declare `db_session` as a parameter and pytest injects it for you —
freshly built, and torn down cleanly after the test finishes.

Design goals for this file:
    1. Every test starts from an EMPTY database (no leakage between tests).
    2. No test touches Redis, real disk, real ML models, or the real network.
    3. The FastAPI app itself is patched so its DB dependency points at the
       in-memory test DB.
"""

from __future__ import annotations

import asyncio
import importlib
import io
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 1.  Force a safe test-time configuration BEFORE importing the app.
# The backend reads a .env file at import time via pydantic-settings.
# We will override the values that would otherwise point at Redis / real DB paths annd we do not want that.
TEST_ROOT = Path(tempfile.mkdtemp(prefix="binp51-tests-"))
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
os.environ["ENV_FILE"] = ".env.test"
os.environ["PROJECT_ROOT"] = str(TEST_ROOT)
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")
os.environ["RESULTS_DIR"] = str(TEST_ROOT / "results")
os.environ["LOGS_DIR"] = str(TEST_ROOT / "logs")
os.environ["RUNTIME_DIR"] = str(TEST_ROOT / "runtime")
os.environ["BACKEND_DB_PATH"] = str(TEST_ROOT / "databases" / "malmo_backend.db")
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Map absolute app imports (`backend.*`) to `src.backend.*` without replacing
# the top-level `backend` test package used by pytest collection.
sys.modules["backend.config"] = importlib.import_module("src.backend.config")
sys.modules["backend.database"] = importlib.import_module("src.backend.database")
sys.modules["backend.models"] = importlib.import_module("src.backend.models")
sys.modules["backend.celery_app"] = importlib.import_module("src.backend.celery_app")

# Now it's safe to import backend modules — they'll pick up the overrides.
from src.backend import crud, main  # noqa: E402
from src.backend.database import Base, get_async_session  # noqa: E402


# 2.  Event loop — one loop per test session (needed for async fixtures).
@pytest.fixture(scope="session")
def event_loop():
    """Create a single asyncio event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# 3.  Database fixtures.
# We use an in-memory SQLite database.  It's created fresh for every single  test (function scope) which guarantees
# test isolation — the golden rule of
# testing databases.
@pytest_asyncio.fixture
async def db_engine():
    """A brand-new async SQLite engine, tables created, torn down after test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    An AsyncSession bound to the fresh in-memory DB.
    Every unit test asking for `db_session` gets its own empty database.
    """
    Session = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with Session() as session:
        yield session


# 4.  FastAPI test client — talks to the app *without* a network socket.
@pytest_asyncio.fixture
async def api_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """
    An httpx AsyncClient wired directly into the FastAPI ASGI app.

    Crucially, we override the `get_async_session` dependency so the app
    uses OUR in-memory test DB instead of the real one from settings.
    """

    async def _override_get_session():
        # Yield the same session the test can inspect/verify against.
        yield db_session

    main.app.dependency_overrides[get_async_session] = _override_get_session

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    main.app.dependency_overrides.clear()


# 5.  Domain fixtures — small factories that produce ready-made objects.
@pytest.fixture
def sample_payload() -> dict:
    """A valid multipart-form payload representing a new sample upload."""
    return {
        "username": "alice",
        "email": "alice@example.com",
        "sample_name": "malmo_park_01",
    }


@pytest.fixture
def fake_fastq_files() -> dict:
    """
    Two tiny in-memory 'FASTQ' files.  Content doesn't matter — the API
    only checks the filename extension and streams bytes to disk.
    """
    r1 = ("malmo_park_01_R1.fastq.gz", io.BytesIO(b"@read1\nACGT\n+\n!!!!\n"), "application/gzip")
    r2 = ("malmo_park_01_R2.fastq.gz", io.BytesIO(b"@read1\nTGCA\n+\n!!!!\n"), "application/gzip")
    return {"r1": r1, "r2": r2}


@pytest_asyncio.fixture
async def created_sample(db_session, sample_payload):
    """A Samples row already persisted — for tests that need pre-existing data."""
    sample = await crud.create_sample(
        db=db_session,
        username=sample_payload["username"],
        email=sample_payload["email"],
        sample_name=sample_payload["sample_name"],
        r1_path="/tmp/r1.fastq.gz",
        r2_path="/tmp/r2.fastq.gz",
    )
    return sample


# 6.  External-service mocks — Celery, ML model, upload directory.
@pytest.fixture(autouse=True)
def mock_celery(monkeypatch):
    """
    Auto-applied to every test.  Replaces `run_pipeline.delay(...)` with a
    stub that returns a fake AsyncResult — so tests never actually push a
    job to Redis.
    """
    fake_task = MagicMock()
    fake_task.id = "fake-task-id-1234"

    fake_delay = MagicMock(return_value=fake_task)
    monkeypatch.setattr("src.backend.main.run_pipeline.delay", fake_delay)
    return fake_delay


@pytest.fixture
def temp_upload_dir(tmp_path, monkeypatch):
    """
    Redirect the backend's UPLOAD_DIR to a pytest-managed temp folder so
    uploaded files land somewhere disposable.
    """
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("src.backend.main.UPLOAD_DIR", upload_dir)
    return upload_dir


@pytest.fixture
def mock_ml_pipeline(monkeypatch):
    """
    Replace `predict.get_pipeline()` with a fake sklearn-like object that
    always returns EPSG:3006 coordinates roughly corresponding to Malmö.
    """
    fake_pipeline = MagicMock()
    fake_pipeline.named_steps = {"zeros_filter": MagicMock(_keep_cols_=["Bacteroides", "Prevotella", "Faecalibacterium"])}
    # SWEREF99 TM coordinates near Malmö → will convert to ~55.6°N, 13.0°E
    fake_pipeline.predict.return_value = [[370000.0, 6165000.0]]

    monkeypatch.setattr("src.backend.predict.get_pipeline", lambda: fake_pipeline)
    return fake_pipeline


# 7.  Static fixture files.
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def bracken_csv_path() -> Path:
    """Path to the tiny Bracken species CSV used by tasks helper tests."""
    return FIXTURES_DIR / "bracken_species.csv"
