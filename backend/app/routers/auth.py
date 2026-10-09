"""Router autentikasi: signup, login, refresh, dan profil pengguna.

Router tidak memuat logika bisnis; seluruh keputusan ada di ``AuthService``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models import (
    ErrorResponse,
    RefreshRequest,
    TokenPair,
    User,
    UserLogin,
    UserPublic,
    UserSignup,
)
from app.repositories import UserRepository
from app.services import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _service(db: Session = Depends(get_db)) -> AuthService:
    """Bangun ``AuthService`` dengan repositori terkait."""
    return AuthService(UserRepository(db))


@router.post(
    "/signup",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Registrasi pengguna baru",
    responses={409: {"model": ErrorResponse, "description": "Email sudah terdaftar"}},
)
def signup(payload: UserSignup, service: AuthService = Depends(_service)) -> TokenPair:
    """Daftarkan pengguna dan langsung terbitkan token pair."""
    _, tokens = service.signup(
        name=payload.name,
        email=str(payload.email),
        password=payload.password,
    )
    return TokenPair(**tokens)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Login dan terbitkan token pair",
    responses={401: {"model": ErrorResponse, "description": "Kredensial salah"}},
)
def login(payload: UserLogin, service: AuthService = Depends(_service)) -> TokenPair:
    """Verifikasi kredensial lalu terbitkan access + refresh token."""
    _, tokens = service.login(email=str(payload.email), password=payload.password)
    return TokenPair(**tokens)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Terbitkan access token baru dari refresh token",
    responses={401: {"model": ErrorResponse, "description": "Refresh token tidak valid"}},
)
def refresh(payload: RefreshRequest, service: AuthService = Depends(_service)) -> TokenPair:
    """Validasi refresh token dan kembalikan token pair baru."""
    tokens = service.refresh(refresh_token=payload.refresh_token)
    return TokenPair(**tokens)


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Profil pengguna yang sedang login (protected)",
    responses={401: {"model": ErrorResponse, "description": "Token tidak valid / tidak ada"}},
)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    """Kembalikan profil pengguna dari klaim token — menolak tanpa Bearer token."""
    return UserPublic.model_validate(current_user)
