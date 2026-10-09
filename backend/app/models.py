"""Model ORM dan skema Pydantic untuk PTM-06.

Model ORM mengikuti ERD PTM-05 dengan dua penyesuaian yang diperlukan agar
autentikasi dan pengecekan kepemilikan objek (anti-BOLA) dapat berjalan:

1. Tabel ``users`` ditambahkan sebagai pemilik data.
2. ``visitor_history.user_id`` dan ``prediction_result.user_id`` ditambahkan
   sebagai kunci kepemilikan yang diverifikasi pada setiap operasi CRUD.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    """Waktu UTC sadar-zona untuk kolom waktu."""
    return datetime.now(tz=timezone.utc)


# ==============================================================================
# ORM MODELS
# ==============================================================================


class User(Base):
    """Pengguna sistem. Password selalu tersimpan sebagai hash bcrypt."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    histories: Mapped[list["VisitorHistory"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["PredictionResult"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class VisitorHistory(Base):
    """Data histori jumlah pengunjung (Entity 1 pada ERD PTM-05)."""

    __tablename__ = "visitor_history"
    __table_args__ = (UniqueConstraint("user_id", "visit_date", name="uq_history_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    visit_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    visit_day: Mapped[str] = mapped_column(String(16), nullable=False)
    visitor_total: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="histories")
    predictions: Mapped[list["PredictionResult"]] = relationship(
        back_populates="history", cascade="all, delete-orphan"
    )


class PredictionResult(Base):
    """Hasil prediksi jumlah pengunjung (Entity 2 pada ERD PTM-05)."""

    __tablename__ = "prediction_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    visitor_history_id: Mapped[int] = mapped_column(
        ForeignKey("visitor_history.id", ondelete="CASCADE"), index=True, nullable=False
    )
    visit_day: Mapped[str] = mapped_column(String(16), nullable=False)
    prediction_value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="predictions")
    history: Mapped[VisitorHistory] = relationship(back_populates="predictions")


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

VALID_DAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)


class UserSignup(BaseModel):
    """Payload POST /auth/signup."""

    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Nama minimal 2 karakter")
        return cleaned

    @field_validator("password")
    @classmethod
    def _strong_password(cls, value: str) -> str:
        if not any(ch.isalpha() for ch in value):
            raise ValueError("Password harus memuat minimal satu huruf")
        if not any(ch.isdigit() for ch in value):
            raise ValueError("Password harus memuat minimal satu angka")
        return value


class UserLogin(BaseModel):
    """Payload POST /auth/login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Payload POST /auth/refresh."""

    refresh_token: str = Field(min_length=10)


class TokenPair(BaseModel):
    """Respons pasangan token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserPublic(BaseModel):
    """Representasi publik pengguna (TANPA password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    created_at: datetime


class VisitorHistoryCreate(BaseModel):
    """Payload POST /api/history."""

    visit_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    visit_day: str
    visitor_total: int = Field(ge=0, le=1_000_000)

    @field_validator("visit_day")
    @classmethod
    def _valid_day(cls, value: str) -> str:
        normalized = value.strip().capitalize()
        if normalized not in VALID_DAYS:
            raise ValueError(f"visit_day harus salah satu dari: {', '.join(VALID_DAYS)}")
        return normalized


class VisitorHistoryUpdate(BaseModel):
    """Payload PUT /api/history/{id} — seluruh field opsional."""

    visit_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    visit_day: str | None = None
    visitor_total: int | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("visit_day")
    @classmethod
    def _valid_day(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().capitalize()
        if normalized not in VALID_DAYS:
            raise ValueError(f"visit_day harus salah satu dari: {', '.join(VALID_DAYS)}")
        return normalized


class VisitorHistoryOut(BaseModel):
    """Representasi keluaran histori pengunjung."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    visit_date: str
    visit_day: str
    visitor_total: int
    created_at: datetime


class PredictionRequest(BaseModel):
    """Payload POST /api/predict (kontrak PTM-05, diperluas)."""

    visit_day: str
    visitor_history_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=512)

    @field_validator("visit_day")
    @classmethod
    def _valid_day(cls, value: str) -> str:
        normalized = value.strip().capitalize()
        if normalized not in VALID_DAYS:
            raise ValueError(f"visit_day harus salah satu dari: {', '.join(VALID_DAYS)}")
        return normalized


class PredictionOut(BaseModel):
    """Respons hasil prediksi."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    visitor_history_id: int
    visit_day: str
    prediction_value: int
    created_at: datetime


class PredictionResponse(BaseModel):
    """Respons utama POST /api/predict (kompatibel dengan kontrak PTM-05)."""

    status: str = "success"
    prediction: int
    visit_day: str
    record_id: int
    model_source: str
    created_at: datetime


class ErrorResponse(BaseModel):
    """Format galat terstandar."""

    status: str = "error"
    message: str


class AIInferenceResponse(BaseModel):
    """Respons endpoint inferensi AI berbasis unggahan berkas."""

    status: str = "success"
    filename: str
    mime_type: str
    size_bytes: int
    prediction: int
    model_source: str
    sanitized: bool = True


class HealthResponse(BaseModel):
    """Respons health check."""

    status: str = "ok"
    app: str
    version: str
    model_loaded: bool


class BatchPredictionRequest(BaseModel):
    """Payload POST /api/predict/batch — dibatasi untuk mencegah penyalahgunaan."""

    visit_days: list[str] = Field(min_length=1, max_length=7)

    @field_validator("visit_days")
    @classmethod
    def _valid_days(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for day in value:
            cleaned = day.strip().capitalize()
            if cleaned not in VALID_DAYS:
                raise ValueError(f"visit_day '{day}' tidak valid")
            normalized.append(cleaned)
        return normalized
