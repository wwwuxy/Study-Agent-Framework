from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/study.db"
    credential_encryption_key: str = ""
    allow_private_provider_urls: bool = False
    enable_fake_provider: bool = False
    cookie_secure: bool = True
    frontend_origin: str = "http://localhost:5173"
    session_hours: int = Field(default=168, ge=1, le=720)
    structured_retries: int = Field(default=2, ge=0, le=3)
    provider_calls_per_minute: int = Field(default=30, ge=1, le=1000)
    frontend_dist: str = "frontend/dist"
    material_storage_dir: str = "data/materials"
    material_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=48 * 1024 * 1024)
    material_max_sections: int = Field(default=20, ge=1, le=40)
    material_worker_enabled: bool = True
    material_job_attempts: int = Field(default=3, ge=1, le=5)
    pgvector_enabled: bool = False
