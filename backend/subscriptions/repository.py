"""Persistence for disease alert subscriptions."""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Mapping, Protocol

from sqlalchemy import select, update

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import disease_alert_subscriptions as subs_table
from .models import AlertPrefs, DiseaseAlertSubscription, SubscriptionStatus


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _prefs_from_json(raw: str) -> AlertPrefs:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return AlertPrefs(
        guidelines=bool(data.get("guidelines", True)),
        trials=bool(data.get("trials", True)),
        therapies=bool(data.get("therapies", False)),
        doctors=bool(data.get("doctors", True)),
    )


def _prefs_to_json(prefs: AlertPrefs) -> str:
    return json.dumps(
        {
            "guidelines": prefs.guidelines,
            "trials": prefs.trials,
            "therapies": prefs.therapies,
            "doctors": prefs.doctors,
        }
    )


def subscription_from_row(row: Mapping[str, object]) -> DiseaseAlertSubscription:
    return DiseaseAlertSubscription(
        id=str(row["id"]),
        disease_slug=str(row["disease_slug"]),
        email=str(row["email"]),
        confirm_token=str(row["confirm_token"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        prefs=_prefs_from_json(str(row.get("prefs_json") or "{}")),
        radius_km=int(row["radius_km"]) if row.get("radius_km") is not None else None,
        created_at=str(row["created_at"]),
        confirmed_at=str(row["confirmed_at"]) if row.get("confirmed_at") else None,
        unsubscribed_at=str(row["unsubscribed_at"]) if row.get("unsubscribed_at") else None,
    )


class SubscriptionRepo(Protocol):
    def upsert_pending(
        self,
        *,
        disease_slug: str,
        email: str,
        confirm_token: str,
        prefs: AlertPrefs,
        radius_km: int | None,
    ) -> DiseaseAlertSubscription: ...

    def get_by_token(self, confirm_token: str) -> DiseaseAlertSubscription | None: ...

    def get_by_slug_email(
        self, disease_slug: str, email: str
    ) -> DiseaseAlertSubscription | None: ...

    def mark_confirmed(self, subscription_id: str) -> DiseaseAlertSubscription | None: ...

    def mark_unsubscribed(self, subscription_id: str) -> DiseaseAlertSubscription | None: ...


class SqlaSubscriptionRepo(BaseSqlalchemyRepo):
    def upsert_pending(
        self,
        *,
        disease_slug: str,
        email: str,
        confirm_token: str,
        prefs: AlertPrefs,
        radius_km: int | None,
    ) -> DiseaseAlertSubscription:
        now = _utc_now_iso()
        with self._conn() as conn:
            existing = conn.execute(
                select(subs_table).where(
                    subs_table.c.disease_slug == disease_slug,
                    subs_table.c.email == email,
                )
            ).mappings().first()
            if existing is not None:
                sub_id = str(existing["id"])
                conn.execute(
                    update(subs_table)
                    .where(subs_table.c.id == sub_id)
                    .values(
                        confirm_token=confirm_token,
                        status="pending",
                        prefs_json=_prefs_to_json(prefs),
                        radius_km=radius_km,
                        confirmed_at=None,
                        unsubscribed_at=None,
                        created_at=now,
                    )
                )
                row = conn.execute(
                    select(subs_table).where(subs_table.c.id == sub_id)
                ).mappings().one()
                return subscription_from_row(dict(row))

            sub_id = str(uuid.uuid4())
            conn.execute(
                subs_table.insert().values(
                    id=sub_id,
                    disease_slug=disease_slug,
                    email=email,
                    confirm_token=confirm_token,
                    status="pending",
                    prefs_json=_prefs_to_json(prefs),
                    radius_km=radius_km,
                    created_at=now,
                    confirmed_at=None,
                    unsubscribed_at=None,
                )
            )
            row = conn.execute(
                select(subs_table).where(subs_table.c.id == sub_id)
            ).mappings().one()
            return subscription_from_row(dict(row))

    def get_by_token(self, confirm_token: str) -> DiseaseAlertSubscription | None:
        with self._conn() as conn:
            row = conn.execute(
                select(subs_table).where(subs_table.c.confirm_token == confirm_token)
            ).mappings().first()
            return subscription_from_row(dict(row)) if row is not None else None

    def get_by_slug_email(
        self, disease_slug: str, email: str
    ) -> DiseaseAlertSubscription | None:
        with self._conn() as conn:
            row = conn.execute(
                select(subs_table).where(
                    subs_table.c.disease_slug == disease_slug,
                    subs_table.c.email == email,
                )
            ).mappings().first()
            return subscription_from_row(dict(row)) if row is not None else None

    def mark_confirmed(self, subscription_id: str) -> DiseaseAlertSubscription | None:
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                update(subs_table)
                .where(subs_table.c.id == subscription_id)
                .values(status="confirmed", confirmed_at=now, unsubscribed_at=None)
            )
            row = conn.execute(
                select(subs_table).where(subs_table.c.id == subscription_id)
            ).mappings().first()
            return subscription_from_row(dict(row)) if row is not None else None

    def mark_unsubscribed(self, subscription_id: str) -> DiseaseAlertSubscription | None:
        now = _utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                update(subs_table)
                .where(subs_table.c.id == subscription_id)
                .values(status="unsubscribed", unsubscribed_at=now)
            )
            row = conn.execute(
                select(subs_table).where(subs_table.c.id == subscription_id)
            ).mappings().first()
            return subscription_from_row(dict(row)) if row is not None else None


class InMemorySubscriptionRepo:
    def __init__(self) -> None:
        self._rows: dict[str, DiseaseAlertSubscription] = {}
        self._by_token: dict[str, str] = {}
        self._by_slug_email: dict[tuple[str, str], str] = {}

    def upsert_pending(
        self,
        *,
        disease_slug: str,
        email: str,
        confirm_token: str,
        prefs: AlertPrefs,
        radius_km: int | None,
    ) -> DiseaseAlertSubscription:
        key = (disease_slug, email)
        now = _utc_now_iso()
        if key in self._by_slug_email:
            sub_id = self._by_slug_email[key]
            old = self._rows[sub_id]
            self._by_token.pop(old.confirm_token, None)
        else:
            sub_id = str(uuid.uuid4())
        sub = DiseaseAlertSubscription(
            id=sub_id,
            disease_slug=disease_slug,
            email=email,
            confirm_token=confirm_token,
            status="pending",
            prefs=prefs,
            radius_km=radius_km,
            created_at=now,
            confirmed_at=None,
            unsubscribed_at=None,
        )
        self._rows[sub_id] = sub
        self._by_token[confirm_token] = sub_id
        self._by_slug_email[key] = sub_id
        return sub

    def get_by_token(self, confirm_token: str) -> DiseaseAlertSubscription | None:
        sub_id = self._by_token.get(confirm_token)
        return self._rows.get(sub_id) if sub_id else None

    def get_by_slug_email(
        self, disease_slug: str, email: str
    ) -> DiseaseAlertSubscription | None:
        sub_id = self._by_slug_email.get((disease_slug, email))
        return self._rows.get(sub_id) if sub_id else None

    def mark_confirmed(self, subscription_id: str) -> DiseaseAlertSubscription | None:
        sub = self._rows.get(subscription_id)
        if sub is None:
            return None
        updated = replace(
            sub,
            status="confirmed",
            confirmed_at=_utc_now_iso(),
            unsubscribed_at=None,
        )
        self._rows[subscription_id] = updated
        return updated

    def mark_unsubscribed(self, subscription_id: str) -> DiseaseAlertSubscription | None:
        sub = self._rows.get(subscription_id)
        if sub is None:
            return None
        updated = replace(
            sub,
            status="unsubscribed",
            unsubscribed_at=_utc_now_iso(),
        )
        self._rows[subscription_id] = updated
        return updated


__all__ = [
    "InMemorySubscriptionRepo",
    "SqlaSubscriptionRepo",
    "SubscriptionRepo",
    "subscription_from_row",
]
