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

    # Celery Configuration
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")

    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////home/chandru/binp51/databases/malmo_backend.db")

    # Application Settings
    PROJECT_ROOT = Path(
        os.getenv(
            "PROJECT_ROOT",
            Path(__file__).resolve().parents[2],  # repo root in development
        )
    )
    UPLOAD_DIR: str = os.path.join(PROJECT_ROOT, "uploads")

    # Machine learning model
    # Need to change this to something much more simpler.
    MODEL_PATH: str = f"{PROJECT_ROOT}/src/ml/mlruns/1/models/m-150112cb0dfd4175b98a23716a7f042b/artifacts/model.pkl"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create a singleton instance
settings = Settings()
