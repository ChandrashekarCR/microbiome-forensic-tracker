"""
Configuration settings for the Microdentify backend.
Used by both FastAPI and Celery worker.
"""

import os
from pathlib import Path


class Settings:
    """
    Celery and database configuration.
    Can be overridden by environment variables.
    """

    # Application Settings
    PROJECT_ROOT = Path(
        os.getenv(
            "PROJECT_ROOT",
            Path(__file__).resolve().parents[2],  # repo root in development
        )
    )

    UPLOAD_DIR: Path = PROJECT_ROOT / os.getenv("UPLOAD_DIR", "uploads")

    RESULTS_DIR: Path = PROJECT_ROOT / os.getenv("RESULTS_DIR", "results")

    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{PROJECT_ROOT}/databases/malmo_backend.db")

    # Celery Configuration
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")

    # Machine learning model
    # Need to change this to something much more simpler.
    MODEL_PATH: str = f"{PROJECT_ROOT}/src/ml/mlruns/1/models/m-150112cb0dfd4175b98a23716a7f042b/artifacts/model.pkl"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create a singleton instance
settings = Settings()
