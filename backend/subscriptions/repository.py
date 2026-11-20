"""Persistence for disease alert subscriptions."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select, update

from ..shared.persistence.base_repo import BaseSqlalchemyRepo
from ..shared.persistence.schema import disease_alert_subscriptions as subs_table
from .models import AlertPrefs, DiseaseAlertSubscription


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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
        community=bool(data.get("community", False)),
    )


def _ref_from_json(raw: str) -> str | None:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    ref = data.get("ref") if isinstance(data, dict) else None
    return str(ref) if ref else None


def _prefs_to_json(prefs: AlertPrefs, client_ref_hash: str | None = None) -> str:
    # The browser reference lives in prefs_json so closing the email lookup needed no migration. Key order is fixed (sort_keys) so the "ref" lookup below can match on the serialised text.
    return json.dumps(
        {
            "guidelines": prefs.guidelines,
            "trials": prefs.trials,
            "therapies": prefs.therapies,
            "doctors": prefs.doctors,
            "community": prefs.community,
            "ref": client_ref_hash,
        },
        sort_keys=True,
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
        client_ref_hash=_ref_from_json(str(row.get("prefs_json") or "{}")),
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
        client_ref_hash: str | None = None,
    ) -> DiseaseAlertSubscription: ...

    def get_by_slug_ref(self, disease_slug: str, client_ref_hash: str) -> DiseaseAlertSubscription | None: ...

    def list_confirmed(self, disease_slug: str) -> list[DiseaseAlertSubscription]: ...

    def delete(self, subscription_id: str) -> None: ...

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
        client_ref_hash: str | None = None,
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
                        prefs_json=_prefs_to_json(prefs, client_ref_hash),
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
                    prefs_json=_prefs_to_json(prefs, client_ref_hash),
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

    def get_by_slug_ref(self, disease_slug: str, client_ref_hash: str) -> DiseaseAlertSubscription | None:
        if not client_ref_hash:
            return None
        with self._conn() as conn:
            rows = conn.execute(
                select(subs_table).where(
                    subs_table.c.disease_slug == disease_slug,
                    subs_table.c.prefs_json.contains(f'"ref": "{client_ref_hash}"'),
                )
            ).mappings().all()
        for row in rows:
            sub = subscription_from_row(dict(row))
            if sub.client_ref_hash == client_ref_hash:
                return sub
        return None

    def list_confirmed(self, disease_slug: str) -> list[DiseaseAlertSubscription]:
        with self._conn() as conn:
            rows = conn.execute(
                select(subs_table).where(
                    subs_table.c.disease_slug == disease_slug,
                    subs_table.c.status == "confirmed",
                )
            ).mappings().all()
        return [subscription_from_row(dict(row)) for row in rows]

    def delete(self, subscription_id: str) -> None:
        with self._conn() as conn:
            conn.execute(delete(subs_table).where(subs_table.c.id == subscription_id))


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
        client_ref_hash: str | None = None,
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
            client_ref_hash=client_ref_hash,
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

    def get_by_slug_ref(self, disease_slug: str, client_ref_hash: str) -> DiseaseAlertSubscription | None:
        return next(
            (
                sub
                for sub in self._rows.values()
                if client_ref_hash and sub.disease_slug == disease_slug and sub.client_ref_hash == client_ref_hash
            ),
            None,
        )

    def list_confirmed(self, disease_slug: str) -> list[DiseaseAlertSubscription]:
        return [sub for sub in self._rows.values() if sub.disease_slug == disease_slug and sub.status == "confirmed"]

    def delete(self, subscription_id: str) -> None:
        sub = self._rows.pop(subscription_id, None)
        if sub is None:
            return
        self._by_token.pop(sub.confirm_token, None)
        self._by_slug_email.pop((sub.disease_slug, sub.email), None)


__all__ = [
    "InMemorySubscriptionRepo",
    "SqlaSubscriptionRepo",
    "SubscriptionRepo",
    "subscription_from_row",
]
