"""Konfigurasi aplikasi.

Semua nilai sensitif dibaca dari environment variable melalui
``pydantic-settings``. Tidak ada nilai rahasia yang di-hardcode di dalam kode
(OWASP API8:2023 - Security Misconfiguration).
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfigurasi runtime backend, dibaca dari file ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Identitas aplikasi ---------------------------------------------------
    APP_NAME: str = "Visitor Prediction API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "REST API Prediksi Jumlah Pengunjung Wisata Religi Makam Gus Dur "
        "(XGBoost + Grid Search). Implementasi backend modular PTM-06."
    )
    DEBUG: bool = False

    # --- Database -------------------------------------------------------------
    DATABASE_URL: str = "sqlite:///./app.db"

    # --- JWT ------------------------------------------------------------------
    SECRET_KEY: str = Field(
        default="change-me-with-a-long-random-secret-key",
        description="Kunci penandatanganan JWT. WAJIB diganti di produksi.",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Model AI -------------------------------------------------------------
    MODEL_PATH: str = "ml/model_xgb.json"
    SCALER_PATH: str = "ml/scaler.pkl"

    # --- Batas sumber daya (OWASP API4:2023) ---------------------------------
    MAX_FILE_SIZE_MB: int = 5
    MAX_TEXT_LENGTH: int = 512

    # --- CORS -----------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def _positive_access_expiry(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES harus lebih dari 0")
        return value

    @field_validator("MAX_FILE_SIZE_MB")
    @classmethod
    def _positive_file_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_FILE_SIZE_MB harus lebih dari 0")
        return value

    @property
    def max_file_size_bytes(self) -> int:
        """Batas ukuran berkas unggahan dalam byte."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        """Daftar origin CORS yang diizinkan."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_default_secret(self) -> bool:
        """True bila SECRET_KEY masih bernilai default (tidak aman)."""
        return self.SECRET_KEY == "change-me-with-a-long-random-secret-key"


@lru_cache
def get_settings() -> Settings:
    """Ambil instance ``Settings`` (di-cache agar dibaca sekali)."""
    return Settings()


settings: Settings = get_settings()
