from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
STORAGE_DIR = BASE_DIR / "storage"
PRODUCTS_STORAGE_DIR = STORAGE_DIR / "products"
UPLOADS_STORAGE_DIR = STORAGE_DIR / "uploads"
DB_PATH = STORAGE_DIR / "pocket3d.sqlite3"
WEB_VIEWER_DIR = PROJECT_ROOT / "web-viewer"


class Settings(BaseSettings):
    APP_NAME: str = "Pocket 3D Showcase API"
    APP_ENV: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # AI & Processing (FR-04, NFR-01, NFR-02)
    AI_MODEL_NAME: str = "u2netp"
    AI_AUTO_FALLBACK: bool = True
    OUTPUT_CANVAS_SIZE: int = 800
    GLOBAL_SCALE_FILL_RATIO: float = 0.82
    WEBP_QUALITY: int = 82
    MAX_WORKERS: int = 4

    # Queue Backend (FR-03: "local" | "redis")
    QUEUE_BACKEND: str = "local"
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_QUEUE_NAME: str = "pocket3d_jobs"

    # Storage Backend (NFR-04: "local" | "s3")
    STORAGE_BACKEND: str = "local"
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = "pocket-3d-showcase"
    S3_REGION: str = "auto"
    S3_PUBLIC_DOMAIN: str = ""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Ensure local directories exist
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
PRODUCTS_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
