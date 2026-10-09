"""Service histori pengunjung (CRUD) dengan verifikasi kepemilikan objek.

Setiap operasi berparameter ID memverifikasi ``resource.user_id ==
current_user.id``; ketidakcocokan ditolak HTTP 403 (patch anti-BOLA).
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.models import User, VisitorHistory
from app.repositories import VisitorHistoryRepository


class HistoryService:
    """Aturan bisnis untuk resource ``visitor_history``."""

    def __init__(self, history_repo: VisitorHistoryRepository) -> None:
        self.history_repo = history_repo

    def list_for_user(self, current_user: User) -> list[VisitorHistory]:
        """Daftar histori milik pengguna yang sedang login."""
        return self.history_repo.list_by_user(current_user.id)

    def create(self, *, current_user: User, visit_date: str, visit_day: str, visitor_total: int) -> VisitorHistory:
        """Buat catatan histori baru untuk pengguna.

        Raises:
            HTTPException 409: bila tanggal kunjungan yang sama sudah ada.
        """
        existing = self.history_repo.get_by_date_for_user(current_user.id, visit_date)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Catatan untuk tanggal kunjungan tersebut sudah ada",
            )
        return self.history_repo.create(
            user_id=current_user.id,
            visit_date=visit_date,
            visit_day=visit_day,
            visitor_total=visitor_total,
        )

    def get_owned(self, history_id: int, current_user: User) -> VisitorHistory:
        """Ambil histori milik pengguna, atau tolak.

        Raises:
            HTTPException 403: bila catatan ada tetapi milik pengguna lain.
            HTTPException 404: bila catatan tidak ditemukan sama sekali.
        """
        record = self.history_repo.get_by_id(history_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data tidak ditemukan",
            )
        if record.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak",
            )
        return record

    def update(self, history_id: int, current_user: User, **fields) -> VisitorHistory:
        """Perbarui histori milik pengguna setelah verifikasi kepemilikan."""
        record = self.get_owned(history_id, current_user)
        return self.history_repo.update(record, **fields)

    def delete(self, history_id: int, current_user: User) -> None:
        """Hapus histori milik pengguna setelah verifikasi kepemilikan."""
        record = self.get_owned(history_id, current_user)
        self.history_repo.delete(record)
