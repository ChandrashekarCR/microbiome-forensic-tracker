"""
Configuration settings for the Microdentify backend.
Used by both FastAPI and Celery worker.
"""

import os


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
    PROJECT_ROOT: str = "/home/chandru/binp51"
    UPLOAD_DIR: str = os.path.join(PROJECT_ROOT, "uploads")

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create a singleton instance
settings = Settings()
