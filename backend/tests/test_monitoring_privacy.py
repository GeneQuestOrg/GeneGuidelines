"""What actually leaves the process: the real Sentry SDK with our options and a transport that keeps the envelopes instead of sending them."""
from __future__ import annotations

import json
import logging

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert

from backend.shared import monitoring


class KeepEnvelopes(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.payloads: list[str] = []

    def capture_envelope(self, envelope):
        self.payloads.extend(item.get_bytes().decode("utf-8", "replace") for item in envelope.items)


@pytest.fixture
def sent():
    transport = KeepEnvelopes()
    for scope in (sentry_sdk.get_global_scope(), sentry_sdk.get_isolation_scope(), sentry_sdk.get_current_scope()):
        scope.clear_breadcrumbs()  # breadcrumbs outlive a re-init; each test starts from none
    sentry_sdk.init(dsn="https://public@sentry.example/1", transport=transport, **monitoring.sentry_options("test"))
    yield transport
    sentry_sdk.flush()
    sentry_sdk.init(auto_enabling_integrations=False)  # no DSN: the SDK is off again for the tests that follow


def _everything(transport: KeepEnvelopes) -> str:
    sentry_sdk.flush()
    return "\n".join(transport.payloads)


def test_sql_parameters_never_reach_sentry(sent):
    # Built at run time, so the address is not in the source lines Sentry sends as context: only a leaked value can put it in the payload.
    email = "@".join(("parent", "example.org"))
    engine = create_engine("sqlite://", hide_parameters=True)
    people = Table("people", MetaData(), Column("id", Integer, primary_key=True), Column("email", String, unique=True))
    people.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(people).values(id=1, email=email))
    try:
        with engine.begin() as conn:
            conn.execute(insert(people).values(id=2, email=email))
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
    payload = _everything(sent)
    assert "IntegrityError" in payload
    assert email not in payload


def test_warning_text_is_not_sent_and_errors_are(sent):
    log = logging.getLogger("backend.routers.geo")
    log.warning("geocoding failed for %r", " ".join(("Nowogród", "Bobrzański")))
    log.error("geocoding failed")
    payload = _everything(sent)
    assert "geocoding failed" in payload
    assert "Nowogród" not in payload


def test_urls_lose_queries_and_passwords(sent):
    secrets = ["Kowal" + "ski", "SECRET" + "1", "Ab/" + "Cd", "SECRET" + "2"]
    sentry_sdk.capture_exception(RuntimeError(f"GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?term={secrets[0]}&api_key={secrets[1]} failed; postgresql+psycopg://gg:{secrets[2]}@ef@db.example:5432/gg; host=db password={secrets[3]}"))
    payload = _everything(sent)
    for secret in secrets:
        assert secret not in payload, secret
    assert json.loads(sent.payloads[0])["exception"]["values"][0]["type"] == "RuntimeError"


def test_no_trace_headers_and_no_tracing_by_default():
    options = monitoring.sentry_options("test")
    assert options["trace_propagation_targets"] == [] and not options["traces_sample_rate"]
    assert options["data_collection"]["database_query_data"] is False


def test_the_production_engine_hides_parameters(monkeypatch):
    from backend import config
    from backend.shared.persistence import engine as engine_module

    monkeypatch.setattr(config, "DB_URL", "postgresql://user:pw@localhost:5432/db")
    built = engine_module._build_engine()
    try:
        assert built.hide_parameters is True
    finally:
        built.dispose()
