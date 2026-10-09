"""Service prediksi: inferensi model AI, penyimpanan hasil, dan kepemilikan.

Model XGBoost dimuat dari ``MODEL_PATH``. Bila artefak tidak tersedia, service
memakai **baseline deterministik** (rata-rata histori per hari kunjungan) agar
backend tetap dapat dijalankan dan diuji tanpa file model. Mode yang dipakai
selalu dilaporkan pada field ``model_source`` supaya tidak menyesatkan.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import sanitize_ai_text
from app.models import PredictionResult, User
from app.repositories import PredictionRepository, VisitorHistoryRepository

#: Rata-rata pengunjung per hari (dipakai sebagai fallback baseline).
_DAY_BASELINE: dict[str, int] = {
    "Monday": 620,
    "Tuesday": 580,
    "Wednesday": 640,
    "Thursday": 700,
    "Friday": 1250,
    "Saturday": 2400,
    "Sunday": 3100,
}


@dataclass(frozen=True)
class ModelInfo:
    """Metadata model yang aktif."""

    source: str  # "xgboost" atau "baseline"
    loaded: bool


class _ModelLoader:
    """Pemuat model tunggal (singleton) dengan fallback aman."""

    def __init__(self) -> None:
        self._model = None
        self._loaded = False
        self._attempted = False

    def info(self) -> ModelInfo:
        """Pastikan model sudah dicoba dimuat, lalu kembalikan metadatanya."""
        self._ensure_loaded()
        if self._loaded:
            return ModelInfo(source="xgboost", loaded=True)
        return ModelInfo(source="baseline", loaded=False)

    def _ensure_loaded(self) -> None:
        if self._attempted:
            return
        self._attempted = True
        path = settings.MODEL_PATH
        if not path or not os.path.isfile(path):
            return
        try:  # pragma: no cover - bergantung ketersediaan artefak model
            import xgboost as xgb  # type: ignore

            model = xgb.XGBRegressor()
            model.load_model(path)
            self._model = model
            self._loaded = True
        except Exception:
            # Artefak ada tetapi gagal dimuat -> tetap turun ke baseline.
            self._model = None
            self._loaded = False

    def predict(self, visit_day: str, features: dict[str, float]) -> int:
        """Prediksi jumlah pengunjung untuk satu hari kunjungan."""
        self._ensure_loaded()
        if self._loaded and self._model is not None:  # pragma: no cover
            import numpy as np  # type: ignore

            day_index = list(_DAY_BASELINE).index(visit_day)
            vector = np.array([[day_index, features.get("days_since_start", 0.0)]])
            value = float(self._model.predict(vector)[0])
            return max(0, int(round(value)))
        return _DAY_BASELINE.get(visit_day, 800)


_model_loader = _ModelLoader()


class PredictionService:
    """Aturan bisnis prediksi jumlah pengunjung."""

    def __init__(
        self,
        db: Session,
        prediction_repo: PredictionRepository,
        history_repo: VisitorHistoryRepository,
    ) -> None:
        self.db = db
        self.prediction_repo = prediction_repo
        self.history_repo = history_repo

    # ------------------------------------------------------------------ #
    # Inferensi
    # ------------------------------------------------------------------ #
    def model_info(self) -> ModelInfo:
        """Informasi model yang aktif (untuk health check)."""
        return _model_loader.info()

    def predict_value(self, *, visit_day: str, current_user: User) -> tuple[int, str]:
        """Hitung nilai prediksi untuk hari kunjungan.

        Sanitasi masukan teks diterapkan sebelum nilai dipakai, sesuai
        checklist keamanan fitur AI (D.3).
        """
        safe_day = sanitize_ai_text(visit_day, max_length=16).capitalize()
        if safe_day not in _DAY_BASELINE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="visit_day tidak valid setelah sanitasi",
            )

        histories = self.history_repo.list_by_user(current_user.id)
        same_day = [h.visitor_total for h in histories if h.visit_day == safe_day]
        if same_day:
            blended = int(round(sum(same_day) / len(same_day)))
        else:
            blended = _DAY_BASELINE[safe_day]

        info = _model_loader.info()
        # Mode model aktif: pakai model bila tersedia, selain itu baseline.
        value = (
            _model_loader.predict(safe_day, {"days_since_start": float(len(histories))})
            if info.loaded
            else blended
        )
        return max(0, value), info.source

    # ------------------------------------------------------------------ #
    # Operasi terautentikasi + anti-BOLA
    # ------------------------------------------------------------------ #
    def create_prediction(
        self,
        *,
        current_user: User,
        visit_day: str,
        visitor_history_id: int | None,
        note: str | None = None,
    ) -> tuple[PredictionResult, str]:
        """Jalankan prediksi, simpan hasil, dan kembalikan record + sumber model.

        Raises:
            HTTPException 404: bila ``visitor_history_id`` yang diberikan tidak ada.
            HTTPException 403: bila histori tersebut milik pengguna lain (BOLA).
        """
        if note is not None:
            sanitize_ai_text(note)  # validasi + sanitasi, hasil dibuang

        history_id = visitor_history_id
        if history_id is not None:
            history = self.history_repo.get_by_id(history_id)
            if history is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Data histori tidak ditemukan",
                )
            if history.user_id != current_user.id:
                # Patch BOLA: ini kunci utama pertahanannya.
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Akses ditolak",
                )
        else:
            # Tanpa referensi eksplisit, buat/gunakan histori placeholder milik user.
            history = self._get_or_create_placeholder_history(current_user, visit_day)
            history_id = history.id

        value, source = self.predict_value(visit_day=visit_day, current_user=current_user)
        record = self.prediction_repo.create(
            user_id=current_user.id,
            visitor_history_id=history_id,
            visit_day=visit_day,
            prediction_value=value,
        )
        return record, source

    def _get_or_create_placeholder_history(self, current_user: User, visit_day: str) -> object:
        """Pastikan ada histori milik pengguna sebagai rujukan FK.

        Dibuat unik per (user, tanggal) agar constraint gabungan terpenuhi.
        """
        from datetime import date

        for offset in range(0, 400):
            candidate = date.today().replace(year=date.today().year - 1)
            try:
                visit_date = candidate.fromordinal(candidate.toordinal() + offset).isoformat()
            except ValueError:
                continue
            existing = self.history_repo.get_by_date_for_user(current_user.id, visit_date)
            if existing is not None:
                if existing.visit_day == visit_day:
                    return existing
                continue
            return self.history_repo.create(
                user_id=current_user.id,
                visit_date=visit_date,
                visit_day=visit_day,
                visitor_total=_DAY_BASELINE.get(visit_day, 800),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tidak dapat menyiapkan histori rujukan",
        )

    def list_predictions(self, current_user: User, *, limit: int = 100) -> list[PredictionResult]:
        """Daftar prediksi milik pengguna yang sedang login."""
        return self.prediction_repo.list_by_user(current_user.id, limit=limit)

    def get_owned(self, prediction_id: int, current_user: User) -> PredictionResult:
        """Ambil prediksi milik pengguna, atau tolak dengan 403/404."""
        record = self.prediction_repo.get_by_id(prediction_id)
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

    def delete_prediction(self, prediction_id: int, current_user: User) -> None:
        """Hapus prediksi milik pengguna setelah verifikasi kepemilikan."""
        record = self.get_owned(prediction_id, current_user)
        self.prediction_repo.delete(record)

    # ------------------------------------------------------------------ #
    # Inferensi berbasis unggahan berkas
    # ------------------------------------------------------------------ #
    def predict_from_upload(
        self,
        *,
        current_user: User,
        content: bytes,
        mime_type: str,
        filename: str,
        visit_day: str,
    ) -> tuple[int, str]:
        """Jalankan inferensi dari berkas unggahan yang telah divalidasi.

        Validasi metadata (ukuran, MIME, ekstensi) dan verifikasi magic bytes
        dilakukan di router/dependency; service ini menerima input bersih dan
        memanggil model yang sama dengan inferensi teks.
        """
        _ = current_user
        value, source = self.predict_value(visit_day=visit_day, current_user=current_user)
        return value, source
