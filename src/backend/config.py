"""
Single source of truth for ALL configuration.
Reads from .env file automatically via pydantic-settings.

Three consumers:
  1. FastAPI  (main.py)       — imports `settings`
  2. Celery   (tasks.py)      — imports `settings`
  3. ML       (predict.py)    — imports `settings`

Snakemake YAML paths are handled separately (see _load_snakemake_config below).
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to .env - works regardless of where Celery/uvicorn is launched from.
# Azure containers should set ENV_FILE=.env.azure; local dev can use .env.local.
ENV_FILE = Path(__file__).resolve().parents[2] / os.getenv("ENV_FILE", ".env.local")


# This is a pydatntic setting, paths are imported from the .env files in the root,
# but the default is mentioned according to lunarc file system
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),  # absolute path now
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    # Core
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

    # I/O paths
    UPLOAD_DIR: Path = Path("uploads")  # relative -> resolved below
    RESULTS_DIR: Path = Path("results")
    LOGS_DIR: Path = Path("logs")
    RUNTIME_DIR: Path = Path("config/runtime")

    # Databases
    BACKEND_DB_PATH: Path = Path("databases/malmo_backend.db")
    # ML_DB_PATH: Path = Path("databases/malmo.db")

    # Database connection string (optional, overrides SQLite paths)
    BACKEND_DB_URL: str | None = None

    # ML model
    MODEL_PATH: Path = Path("src/ml/mlruns/1/models/m-150112cb0dfd4175b98a23716a7f042b/artifacts/model.pkl")

    # Celery / Redis
    CELERY_BROKER_URL: str = "redis://127.0.0.1:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://127.0.0.1:6379/0"

    # Snakemake
    SNAKEMAKE_PROFILE: str = "profiles/single_run/"
    SNAKEMAKE_CONFIG: str = "config/config_single_run.yaml"
    SNAKEMAKE_BIN: str = "snakemake"
    SNAKEMAKE_TOOLS: str = "bin/"

    # Reference databases (large, HPC/cloud paths)
    KRAKEN2_DB: str = "/lunarc/nobackup/projects/snic2019-34-3/Daria/core_nt_Database"
    HUMAN_GENOME_DIR: str = "/lunarc/nobackup/projects/snic2019-34-3/Daria/CAMP/ref_Human_hg38/ref_Human_hg38/hg38_ref"
    HUMAN_GENOME_INDEX: str = "hg38_index"

    # Derived paths (always absolute, computed from PROJECT_ROOT)
    # These are properties so they update automatically when PROJECT_ROOT changes.

    @property
    def upload_dir(self) -> Path:
        p = self.UPLOAD_DIR
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    @property
    def results_dir(self) -> Path:
        p = self.RESULTS_DIR
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    @property
    def logs_dir(self) -> Path:
        p = self.LOGS_DIR
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    @property
    def runtime_dir(self) -> Path:
        p = self.RUNTIME_DIR
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    @property
    def backend_db_path(self) -> Path:
        p = self.BACKEND_DB_PATH
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    # @property
    # def ml_db_path(self) -> Path:
    #    p = self.ML_DB_PATH
    #    return p if p.is_absolute() else self.PROJECT_ROOT / p

    @property
    def model_path(self) -> Path:
        p = self.MODEL_PATH
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    @property
    def snakefile(self) -> Path:
        return self.PROJECT_ROOT / "workflow" / "Snakefile"

    @property
    def snakemake_profile(self) -> Path:
        return self.PROJECT_ROOT / self.SNAKEMAKE_PROFILE

    @property
    def snakemake_config(self) -> Path:
        return self.PROJECT_ROOT / self.SNAKEMAKE_CONFIG

    @property
    def snakemake_tools(self) -> Path:
        p = self.SNAKEMAKE_TOOLS
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    # SQLAlchemy URLs (derived from db paths)
    @property
    def database_url_async(self) -> str:
        if self.BACKEND_DB_URL:
            # Convert postgresql:// → postgresql+asyncpg:// for async usage
            if self.BACKEND_DB_URL.startswith("postgresql"):
                return self.BACKEND_DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
            return self.BACKEND_DB_URL
        return f"sqlite+aiosqlite:///{self.backend_db_path}"

    @property
    def database_url_sync(self) -> str:
        if self.BACKEND_DB_URL:
            url = self.BACKEND_DB_URL
            # Ensure sync driver for SQLAlchemy
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+psycopg2://", 1)
            if url.startswith("postgresql+asyncpg://"):
                return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
            return url
        return f"sqlite:///{self.backend_db_path}"

    def ensure_directories(self) -> None:
        """Call once at startup to create all required directories."""
        for d in (self.upload_dir, self.logs_dir, self.runtime_dir, self.backend_db_path.parent):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
