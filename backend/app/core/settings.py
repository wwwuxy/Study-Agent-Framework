from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_MATERIAL_BYTES = 1024 * 1024 * 1024


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
    material_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=MAX_MATERIAL_BYTES)
    material_max_sections: int = Field(default=20, ge=1, le=40)
    material_worker_enabled: bool = True
    material_job_attempts: int = Field(default=3, ge=1, le=5)
    pgvector_enabled: bool = False
    learner_parameters_path: str | None = None
    exam_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    exam_worker_enabled: bool = True
    exam_max_images: int = Field(default=20, ge=1, le=20)
    exam_max_questions: int = Field(default=200, ge=1, le=200)
    exam_job_attempts: int = Field(default=3, ge=1, le=5)
    exam_max_output_tokens: int = Field(default=32000, ge=1000, le=64000)
    exam_call_timeout_seconds: int = Field(default=120, ge=10, le=120)
    m4_worker_enabled: bool = True
    m4_tick_seconds: int = Field(default=60, ge=1, le=3600)
    m4_analysis_daily_call_limit: int = Field(default=10, ge=0, le=1000)
    m4_analysis_daily_token_limit: int = Field(default=100000, ge=0)
    m4_analysis_max_output_tokens: int = Field(default=1500, ge=128, le=6000)
    m4_analysis_max_input_bytes: int = Field(default=48000, ge=2048, le=100000)
