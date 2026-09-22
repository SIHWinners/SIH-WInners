"""Runtime settings. Every external dependency has a mode switch; defaults are the
offline-safe sandbox/local variants so a fresh clone runs with zero credentials."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CORE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = CORE_DIR.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(CORE_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["dev", "test", "demo", "prod"] = "dev"
    app_name: str = "SchemeMitra Core"
    public_base_url: str = "http://localhost:3000"
    core_base_url: str = "http://localhost:8000"
    gateway_internal_url: str = "http://localhost:8080"
    internal_shared_secret: str = "dev-internal-secret-change-me"  # noqa: S105

    # storage profile (ADR-001)
    database_url: str = f"sqlite+aiosqlite:///{(CORE_DIR / 'var' / 'schememitra.db').as_posix()}"
    redis_url: str | None = None
    storage_mode: Literal["local", "s3"] = "local"
    storage_dir: Path = CORE_DIR / "var" / "objects"
    s3_endpoint: str | None = None
    s3_bucket: str = "schememitra"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # security
    auth_mode: Literal["dev", "supabase"] = "dev"
    jwt_secret: str = "dev-jwt-secret-please-change-0123456789abcdef"  # noqa: S105
    jwt_ttl_minutes: int = 12 * 60
    # base64 32-byte key-encryption key; data keys are wrapped with it (envelope encryption)
    data_kek_b64: str = "ZGV2LWtleS1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcyE="
    hash_salt: str = "dev-salt-rotate-in-prod"
    qr_signing_key_path: Path = CORE_DIR / "var" / "keys" / "qr_ed25519.pem"
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_lockout_minutes: int = 15
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"])

    # adapters (spec §13)
    bhashini_mode: Literal["sandbox", "real"] = "sandbox"
    bhashini_user_id: str | None = None
    bhashini_api_key: str | None = None
    bhashini_pipeline_id: str = "64392f96daac500b55c543cd"
    asr_fallback: Literal["whisper", "none"] = "whisper"
    whisper_model: str = "small"
    digilocker_mode: Literal["sandbox", "real"] = "sandbox"
    digilocker_client_id: str | None = None
    digilocker_client_secret: str | None = None
    digilocker_redirect_uri: str = "http://localhost:3000/digilocker/callback"
    sms_mode: Literal["console", "msg91", "twilio"] = "console"
    msg91_auth_key: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from: str | None = None
    llm_mode: Literal["off", "ollama", "openai_compat"] = "off"
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    llm_api_key: str | None = None
    llm_timeout_s: float = 8.0
    ocr_mode: Literal["sandbox", "rapidocr"] = "sandbox"
    # Trained by ml/train.py; the feature schema must sit next to it.
    ranking_model_path: Path = CORE_DIR / "app" / "modules" / "ranking" / "model" / "ranker.json"

    # tunables
    external_timeout_s: float = 4.0
    readiness_threshold: int = 70
    partner_recovery_floor: float = 0.70
    partner_cache_ttl_s: int = 600
    k_anonymity_min: int = 10
    image_purge_hours: int = 72
    demo_mode: bool = True

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
