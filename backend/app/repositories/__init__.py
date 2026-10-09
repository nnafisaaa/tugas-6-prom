"""Lapisan repository: HANYA menangani query basis data.

Tidak ada logika bisnis atau keputusan otorisasi di lapisan ini.
Setiap query pada resource milik pengguna WAJIB menyertakan filter ``user_id``
sebagai pertahanan berlapis terhadap BOLA (defense in depth).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PredictionResult, User, VisitorHistory


class UserRepository:
    """Query terkait tabel ``users``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower().strip())
        return self.db.scalars(stmt).first()

    def create(self, *, name: str, email: str, hashed_password: str) -> User:
        user = User(name=name, email=email.lower().strip(), hashed_password=hashed_password)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user


class VisitorHistoryRepository:
    """Query terkait tabel ``visitor_history``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_user(self, user_id: int) -> list[VisitorHistory]:
        stmt = (
            select(VisitorHistory)
            .where(VisitorHistory.user_id == user_id)
            .order_by(VisitorHistory.visit_date.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, history_id: int) -> VisitorHistory | None:
        return self.db.get(VisitorHistory, history_id)

    def get_by_id_for_user(self, history_id: int, user_id: int) -> VisitorHistory | None:
        """Ambil histori HANYA bila dimiliki ``user_id`` (filter di level query)."""
        stmt = select(VisitorHistory).where(
            VisitorHistory.id == history_id,
            VisitorHistory.user_id == user_id,
        )
        return self.db.scalars(stmt).first()

    def get_by_date_for_user(self, user_id: int, visit_date: str) -> VisitorHistory | None:
        stmt = select(VisitorHistory).where(
            VisitorHistory.user_id == user_id,
            VisitorHistory.visit_date == visit_date,
        )
        return self.db.scalars(stmt).first()

    def create(
        self, *, user_id: int, visit_date: str, visit_day: str, visitor_total: int
    ) -> VisitorHistory:
        history = VisitorHistory(
            user_id=user_id,
            visit_date=visit_date,
            visit_day=visit_day,
            visitor_total=visitor_total,
        )
        self.db.add(history)
        self.db.commit()
        self.db.refresh(history)
        return history

    def update(self, history: VisitorHistory, **fields) -> VisitorHistory:
        for key, value in fields.items():
            if value is not None:
                setattr(history, key, value)
        self.db.commit()
        self.db.refresh(history)
        return history

    def delete(self, history: VisitorHistory) -> None:
        self.db.delete(history)
        self.db.commit()


class PredictionRepository:
    """Query terkait tabel ``prediction_result``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_user(self, user_id: int, *, limit: int = 100) -> list[PredictionResult]:
        stmt = (
            select(PredictionResult)
            .where(PredictionResult.user_id == user_id)
            .order_by(PredictionResult.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, prediction_id: int) -> PredictionResult | None:
        return self.db.get(PredictionResult, prediction_id)

    def get_by_id_for_user(self, prediction_id: int, user_id: int) -> PredictionResult | None:
        """Ambil prediksi HANYA bila dimiliki ``user_id``."""
        stmt = select(PredictionResult).where(
            PredictionResult.id == prediction_id,
            PredictionResult.user_id == user_id,
        )
        return self.db.scalars(stmt).first()

    def create(
        self,
        *,
        user_id: int,
        visitor_history_id: int,
        visit_day: str,
        prediction_value: int,
    ) -> PredictionResult:
        prediction = PredictionResult(
            user_id=user_id,
            visitor_history_id=visitor_history_id,
            visit_day=visit_day,
            prediction_value=prediction_value,
        )
        self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)
        return prediction

    def delete(self, prediction: PredictionResult) -> None:
        self.db.delete(prediction)
        self.db.commit()

    def count_by_user(self, user_id: int) -> int:
        stmt = select(PredictionResult).where(PredictionResult.user_id == user_id)
        return len(list(self.db.scalars(stmt).all()))
