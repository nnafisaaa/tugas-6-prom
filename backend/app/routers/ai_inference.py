"""Router inferensi AI berbasis unggahan berkas (*).

Menerapkan kontrol OWASP API4:2023 (Unrestricted Resource Consumption):
- batas ukuran berkas ≤ ``MAX_FILE_SIZE_MB`` (default 5 MB),
- whitelist MIME (``image/jpeg``, ``image/png``),
- penolakan ekstensi berbahaya,
- verifikasi magic bytes untuk mencegah MIME spoofing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import sanitize_ai_text, validate_upload, verify_file_signature
from app.dependencies import get_current_user
from app.models import AIInferenceResponse, ErrorResponse, User
from app.repositories import PredictionRepository, VisitorHistoryRepository
from app.services import PredictionService

router = APIRouter(prefix="/api/ai", tags=["AI Inference (Upload)"])


def _service(db: Session = Depends(get_db)) -> PredictionService:
    return PredictionService(db, PredictionRepository(db), VisitorHistoryRepository(db))


@router.post(
    "/infer",
    response_model=AIInferenceResponse,
    summary="[AI] Inferensi dari berkas unggahan (disanitasi)",
    responses={
        400: {"model": ErrorResponse, "description": "Metadata berkas tidak valid"},
        401: {"model": ErrorResponse, "description": "Tidak terautentikasi"},
        413: {"model": ErrorResponse, "description": "Berkas melebihi batas ukuran"},
        415: {"model": ErrorResponse, "description": "Tipe berkas tidak diizinkan"},
    },
)
async def infer_from_file(
    file: UploadFile = File(..., description="Berkas gambar (JPEG/PNG, maksimal 5 MB)"),
    visit_day: str = Form(..., description="Hari kunjungan target"),
    current_user: User = Depends(get_current_user),
    service: PredictionService = Depends(_service),
) -> AIInferenceResponse:
    """Validasi berkas unggahan, lalu jalankan inferensi model AI."""
    raw = await file.read()

    if len(raw) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Ukuran berkas melebihi batas {settings.MAX_FILE_SIZE_MB} MB",
        )

    try:
        mime_type, _safe_ext = validate_upload(file.content_type, file.filename, len(raw))
        verify_file_signature(raw, mime_type)
    except ValueError as exc:
        message = str(exc)
        code = (
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            if "MIME" in message or "tipe" in message.lower() or "Ekstensi" in message
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=message) from exc

    safe_day = sanitize_ai_text(visit_day, max_length=16).capitalize()
    value, source = service.predict_from_upload(
        current_user=current_user,
        content=raw,
        mime_type=mime_type,
        filename=file.filename or "upload",
        visit_day=safe_day,
    )

    return AIInferenceResponse(
        status="success",
        filename=file.filename or "upload",
        mime_type=mime_type,
        size_bytes=len(raw),
        prediction=value,
        model_source=source,
        sanitized=True,
    )
