"""Dependency bersama: sesi DB, pengguna terautentikasi (protected route).

``get_current_user`` mengekstrak dan memvalidasi Bearer JWT; request tanpa
token valid ditolak dengan HTTP 401 (OWASP API2:2023 - Broken Authentication).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenError, decode_token
from app.models import User

#: ``auto_error=False`` agar kita dapat mengembalikan pesan 401 yang konsisten.
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Ambil pengguna saat ini dari header ``Authorization: Bearer <token>``.

    Raises:
        HTTPException 401: bila header tidak ada, token invalid/kedaluwarsa,
            atau pengguna sudah tidak ada.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kredensial tidak valid atau tidak disertakan",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise unauthorized

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError:
        raise unauthorized from None

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise unauthorized

    return user


def get_owned_or_403(resource, current_user: User):
    """Verifikasi kepemilikan objek — inti patch anti-BOLA.

    Objek yang ada tetapi bukan milik ``current_user`` ditolak dengan HTTP 403,
    bukan 404, sesuai aturan pada prompt D.3.

    Raises:
        HTTPException 404: bila ``resource`` None.
        HTTPException 403: bila kepemilikan tidak cocok.
    """
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data tidak ditemukan")
    if resource.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Akses ditolak")
    return resource
