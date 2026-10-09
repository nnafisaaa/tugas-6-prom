"""Service autentikasi: signup, login, refresh, dan profil.

Seluruh aturan bisnis autentikasi berada di lapisan ini; router hanya
meneruskan request dan membentuk respons HTTP.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.security import (
    TokenError,
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.repositories import UserRepository


class AuthService:
    """Aturan bisnis autentikasi dan manajemen identitas."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    def signup(self, *, name: str, email: str, password: str) -> tuple[User, dict]:
        """Daftarkan pengguna baru.

        Raises:
            HTTPException 409: bila email sudah terdaftar.
        """
        if self.user_repo.get_by_email(email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email sudah terdaftar",
            )

        user = self.user_repo.create(
            name=name,
            email=email,
            hashed_password=hash_password(password),
        )
        return user, create_token_pair(user.id)

    def login(self, *, email: str, password: str) -> tuple[User, dict]:
        """Verifikasi kredensial dan terbitkan token pair.

        Raises:
            HTTPException 401: bila email tidak ditemukan atau password salah.
            Pesan galat disamakan untuk kedua kasus agar tidak membocorkan
            keberadaan akun (user enumeration).
        """
        user = self.user_repo.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email atau password salah",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user, create_token_pair(user.id)

    def refresh(self, *, refresh_token: str) -> dict:
        """Terbitkan access token baru dari refresh token yang valid.

        Raises:
            HTTPException 401: bila refresh token invalid/kedaluwarsa atau
                pengguna sudah tidak ada.
        """
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except TokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token tidak valid atau telah kedaluwarsa",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

        user = self.user_repo.get_by_id(int(payload["sub"]))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Pengguna tidak ditemukan",
            )
        return create_token_pair(user.id)
