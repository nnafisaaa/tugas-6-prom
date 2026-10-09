"""Router histori pengunjung (CRUD) — setiap endpoint terproteksi JWT.

Operasi berparameter ID memakai ``HistoryService.get_owned`` yang
memverifikasi kepemilikan objek (anti-BOLA).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models import (
    ErrorResponse,
    User,
    VisitorHistoryCreate,
    VisitorHistoryOut,
    VisitorHistoryUpdate,
)
from app.repositories import VisitorHistoryRepository
from app.services import HistoryService

router = APIRouter(prefix="/api/history", tags=["Visitor History (CRUD)"])

_AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Tidak terautentikasi"},
    403: {"model": ErrorResponse, "description": "Akses ditolak (bukan pemilik objek)"},
    404: {"model": ErrorResponse, "description": "Data tidak ditemukan"},
}


def _service(db: Session = Depends(get_db)) -> HistoryService:
    return HistoryService(VisitorHistoryRepository(db))


@router.get(
    "",
    response_model=list[VisitorHistoryOut],
    summary="Daftar histori pengunjung milik pengguna",
    responses={401: _AUTH_RESPONSES[401]},
)
def list_history(
    current_user: User = Depends(get_current_user),
    service: HistoryService = Depends(_service),
) -> list[VisitorHistoryOut]:
    """Hanya mengembalikan data milik pengguna yang login."""
    records = service.list_for_user(current_user)
    return [VisitorHistoryOut.model_validate(r) for r in records]


@router.post(
    "",
    response_model=VisitorHistoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Buat catatan histori pengunjung",
    responses={
        401: _AUTH_RESPONSES[401],
        409: {"model": ErrorResponse, "description": "Tanggal kunjungan duplikat"},
    },
)
def create_history(
    payload: VisitorHistoryCreate,
    current_user: User = Depends(get_current_user),
    service: HistoryService = Depends(_service),
) -> VisitorHistoryOut:
    """Simpan data histori baru dengan ``user_id`` dari token (bukan dari body)."""
    record = service.create(
        current_user=current_user,
        visit_date=payload.visit_date,
        visit_day=payload.visit_day,
        visitor_total=payload.visitor_total,
    )
    return VisitorHistoryOut.model_validate(record)


@router.get(
    "/{history_id}",
    response_model=VisitorHistoryOut,
    summary="Ambil detail histori pengunjung",
    responses=_AUTH_RESPONSES,
)
def get_history(
    history_id: int,
    current_user: User = Depends(get_current_user),
    service: HistoryService = Depends(_service),
) -> VisitorHistoryOut:
    """Verifikasi kepemilikan objek sebelum mengembalikan data (anti-BOLA)."""
    record = service.get_owned(history_id, current_user)
    return VisitorHistoryOut.model_validate(record)


@router.put(
    "/{history_id}",
    response_model=VisitorHistoryOut,
    summary="Perbarui histori pengunjung",
    responses=_AUTH_RESPONSES,
)
def update_history(
    history_id: int,
    payload: VisitorHistoryUpdate,
    current_user: User = Depends(get_current_user),
    service: HistoryService = Depends(_service),
) -> VisitorHistoryOut:
    """Perbarui data HANYA bila objek milik pengguna, selain itu HTTP 403."""
    record = service.update(
        history_id,
        current_user,
        visit_date=payload.visit_date,
        visit_day=payload.visit_day,
        visitor_total=payload.visitor_total,
    )
    return VisitorHistoryOut.model_validate(record)


@router.delete(
    "/{history_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus histori pengunjung",
    responses=_AUTH_RESPONSES,
)
def delete_history(
    history_id: int,
    current_user: User = Depends(get_current_user),
    service: HistoryService = Depends(_service),
) -> None:
    """Hapus data HANYA bila objek milik pengguna, selain itu HTTP 403."""
    service.delete(history_id, current_user)
