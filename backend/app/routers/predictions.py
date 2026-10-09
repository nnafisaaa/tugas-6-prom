"""Router prediksi AI (*) dan CRUD hasil prediksi.

Endpoint AI ditandai bintang pada LKP. Setiap operasi berparameter ID
memverifikasi kepemilikan objek (anti-BOLA).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models import (
    BatchPredictionRequest,
    ErrorResponse,
    PredictionOut,
    PredictionRequest,
    PredictionResponse,
    User,
)
from app.repositories import PredictionRepository, VisitorHistoryRepository
from app.services import PredictionService

router = APIRouter(prefix="/api", tags=["Prediction (AI) & CRUD"])

_AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Tidak terautentikasi"},
    403: {"model": ErrorResponse, "description": "Akses ditolak (bukan pemilik objek)"},
    404: {"model": ErrorResponse, "description": "Data tidak ditemukan"},
}


def _service(db: Session = Depends(get_db)) -> PredictionService:
    return PredictionService(db, PredictionRepository(db), VisitorHistoryRepository(db))


@router.post(
    "/predict",
    response_model=PredictionResponse,
    summary="[AI] Prediksi jumlah pengunjung (XGBoost)",
    responses=_AUTH_RESPONSES,
)
def predict(
    payload: PredictionRequest,
    current_user: User = Depends(get_current_user),
    service: PredictionService = Depends(_service),
) -> PredictionResponse:
    """Jalankan model untuk satu hari kunjungan dan simpan hasilnya.

    Bila ``visitor_history_id`` dikirim dan bukan milik pengguna, request
    ditolak HTTP 403 (patch BOLA).
    """
    record, source = service.create_prediction(
        current_user=current_user,
        visit_day=payload.visit_day,
        visitor_history_id=payload.visitor_history_id,
        note=payload.note,
    )
    return PredictionResponse(
        status="success",
        prediction=record.prediction_value,
        visit_day=record.visit_day,
        record_id=record.id,
        model_source=source,
        created_at=record.created_at,
    )


@router.post(
    "/predict/batch",
    response_model=list[PredictionResponse],
    summary="[AI] Prediksi batch (maksimal 7 hari)",
    responses={
        401: _AUTH_RESPONSES[401],
        422: {"model": ErrorResponse, "description": "Jumlah item melebihi batas"},
    },
)
def predict_batch(
    payload: BatchPredictionRequest,
    current_user: User = Depends(get_current_user),
    service: PredictionService = Depends(_service),
) -> list[PredictionResponse]:
    """Prediksi beberapa hari sekaligus, dibatasi untuk mencegah penyalahgunaan."""
    results: list[PredictionResponse] = []
    for day in payload.visit_days:
        record, source = service.create_prediction(
            current_user=current_user,
            visit_day=day,
            visitor_history_id=None,
        )
        results.append(
            PredictionResponse(
                status="success",
                prediction=record.prediction_value,
                visit_day=record.visit_day,
                record_id=record.id,
                model_source=source,
                created_at=record.created_at,
            )
        )
    return results


@router.get(
    "/predictions",
    response_model=list[PredictionOut],
    summary="Daftar hasil prediksi milik pengguna",
    responses={401: _AUTH_RESPONSES[401]},
)
def list_predictions(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    service: PredictionService = Depends(_service),
) -> list[PredictionOut]:
    """Kembalikan prediksi milik pengguna (limit dibatasi 1..500)."""
    safe_limit = max(1, min(limit, 500))
    records = service.list_predictions(current_user, limit=safe_limit)
    return [PredictionOut.model_validate(r) for r in records]


@router.get(
    "/predictions/{prediction_id}",
    response_model=PredictionOut,
    summary="Detail hasil prediksi",
    responses=_AUTH_RESPONSES,
)
def get_prediction(
    prediction_id: int,
    current_user: User = Depends(get_current_user),
    service: PredictionService = Depends(_service),
) -> PredictionOut:
    """Verifikasi kepemilikan sebelum mengembalikan detail (patch BOLA)."""
    record = service.get_owned(prediction_id, current_user)
    return PredictionOut.model_validate(record)


@router.delete(
    "/predictions/{prediction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus hasil prediksi",
    responses=_AUTH_RESPONSES,
)
def delete_prediction(
    prediction_id: int,
    current_user: User = Depends(get_current_user),
    service: PredictionService = Depends(_service),
) -> None:
    """Hapus prediksi HANYA bila milik pengguna, selain itu HTTP 403."""
    service.delete_prediction(prediction_id, current_user)
