"""Pengujian autentikasi JWT (D.2).

Membuktikan: password di-hash bcrypt, token pair terbit, protected route
menolak tanpa token (401), dan refresh token menolak access token (401).
"""

from __future__ import annotations

from jose import jwt

from app.core.config import settings
from tests.conftest import auth_header, signup_user


def test_signup_returns_token_pair_and_hashes_password(client):
    tokens = signup_user(client, name="Nafisa", email="nafisa@example.com")

    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # Password tidak boleh muncul di mana pun pada respons.
    assert "Secret123" not in str(tokens)


def test_password_is_stored_as_bcrypt_hash(client):
    signup_user(client, name="Nafisa", email="hash@example.com")

    from app.models import User
    from tests.conftest import TestSessionLocal

    with TestSessionLocal() as db:
        user = db.query(User).filter(User.email == "hash@example.com").one()

    assert user.hashed_password != "Secret123"
    assert user.hashed_password.startswith("$2")  # penanda hash bcrypt


def test_jwt_claims_do_not_leak_secrets(client):
    tokens = signup_user(client, name="Nafisa", email="claims@example.com")

    payload = jwt.decode(
        tokens["access_token"],
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    assert payload["type"] == "access"
    assert "sub" in payload
    # Tidak ada kunci sensitif pada claims.
    for forbidden in ("password", "hashed_password", "secret", "SECRET_KEY"):
        assert forbidden not in payload


def test_duplicate_email_is_rejected_with_409(client):
    signup_user(client, name="Nafisa", email="dup@example.com")
    response = client.post(
        "/auth/signup",
        json={"name": "Lain", "email": "dup@example.com", "password": "Secret123"},
    )
    assert response.status_code == 409


def test_weak_password_is_rejected_with_422(client):
    response = client.post(
        "/auth/signup",
        json={"name": "Nafisa", "email": "weak@example.com", "password": "semuaHuruf"},
    )
    assert response.status_code == 422


def test_invalid_email_is_rejected_with_422(client):
    response = client.post(
        "/auth/signup",
        json={"name": "Nafisa", "email": "bukan-email", "password": "Secret123"},
    )
    assert response.status_code == 422


def test_login_success_and_wrong_password(client):
    signup_user(client, name="Nafisa", email="login@example.com")

    ok = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "Secret123"},
    )
    assert ok.status_code == 200
    assert "access_token" in ok.json()

    bad = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "PasswordSalah1"},
    )
    assert bad.status_code == 401


def test_login_unknown_email_returns_401_without_enumeration(client):
    response = client.post(
        "/auth/login",
        json={"email": "tidakada@example.com", "password": "Secret123"},
    )
    assert response.status_code == 401
    # Pesan tidak membedakan akun ada/tidak ada.
    assert "salah" in response.json()["message"].lower()


def test_me_requires_bearer_token(client):
    signup_user(client, name="Nafisa", email="me@example.com")

    # Tanpa token -> 401
    assert client.get("/auth/me").status_code == 401

    # Token ngawur -> 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer ngawur"}).status_code == 401

    # Skema salah -> 401
    assert client.get("/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_me_returns_own_profile_with_valid_token(client):
    tokens = signup_user(client, name="Nafisa", email="profile@example.com")
    response = client.get("/auth/me", headers=auth_header(tokens))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "profile@example.com"
    assert body["name"] == "Nafisa"
    assert "hashed_password" not in body  # tidak membocorkan hash


def test_refresh_issues_new_access_token(client):
    tokens = signup_user(client, name="Nafisa", email="refresh@example.com")
    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"]
    assert client.get("/auth/me", headers=auth_header(new_tokens)).status_code == 200


def test_refresh_rejects_access_token_with_401(client):
    """Access token tidak boleh dipakai sebagai refresh token (pemisahan tipe)."""
    tokens = signup_user(client, name="Nafisa", email="typec@example.com")
    response = client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert response.status_code == 401


def test_refresh_rejects_garbage_token_with_401(client):
    response = client.post("/auth/refresh", json={"refresh_token": "ini.bukan.jwt"})
    assert response.status_code == 401
