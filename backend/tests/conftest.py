"""Konfigurasi bersama untuk pengujian: fixture klien, DB terisolasi, pengguna.

Basis data pengujian memakai SQLite in-memory yang terpisah per sesi uji,
sehingga tidak mengotori DB pengembangan dan selalu bersih tiap kali dijalankan.
"""

from __future__ import annotations

import os

# Wajib diset SEBELUM mengimpor app agar Settings membaca nilai uji ini.
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production-0123456789")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_app.db")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# Engine in-memory dengan StaticPool agar satu koneksi dipakai bersama.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    """Klien HTTP yang menguji aplikasi tanpa menjalankan server jaringan."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_tables():
    """Kosongkan tabel sebelum tiap pengujian agar hasilnya independen."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


# ------------------------------------------------------------------------------
# Helper pembuatan pengguna & header
# ------------------------------------------------------------------------------


def signup_user(client: TestClient, *, name: str, email: str, password: str = "Secret123") -> dict:
    """Daftarkan pengguna dan kembalikan token pair."""
    response = client.post(
        "/auth/signup",
        json={"name": name, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_header(tokens: dict) -> dict:
    """Bangun header Authorization dari token pair."""
    return {"Authorization": f"Bearer {tokens['access_token']}"}
