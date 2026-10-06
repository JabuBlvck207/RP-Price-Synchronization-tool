"""Application configuration via environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PCR_", env_file=".env", extra="ignore")

    app_name: str = "Product Catalog Reconciliation Platform"
    app_version: str = "2.1.0"
    debug: bool = True

    # Paths
    base_dir: Path = Path(__file__).resolve().parents[2]
    upload_dir: Path = base_dir / "data" / "uploads"
    output_dir: Path = base_dir / "data" / "outputs"

    # Database – set PCR_USE_SQLITE=true for local dev without Postgres
    use_sqlite: bool = True  # default True for easy local start; set false in production
    database_url: str = "postgresql+asyncpg://pcr:pcr@localhost:5432/pcr"
    database_url_sync: str = "postgresql://pcr:pcr@localhost:5432/pcr"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Matching defaults
    fuzzy_threshold: float = 85.0
    auto_match_min_score: float = 85.0

    # File limits
    max_upload_size_mb: int = 100
    allowed_extensions: set[str] = {".csv", ".xlsx", ".xls", ".pdf"}

    # Security
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    access_token_expire_minutes: int = 60 * 24


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
# Ensure data dir exists for SQLite
(settings.base_dir / "data").mkdir(parents=True, exist_ok=True)
