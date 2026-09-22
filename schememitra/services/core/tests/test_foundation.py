import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core import audit
from app.core.crypto import decrypt_str, encrypt_str, keyed_hash, normalize_phone, phone_hash
from app.core.ids import (
    ALPHABET,
    is_valid_tracking_id,
    luhn_mod_n_check_char,
    new_tracking_id,
    normalize_tracking_id,
    uuid7,
)
from app.logging import scrub, scrub_text
from tests.conftest import login


def test_uuid7_is_version_7_and_time_ordered() -> None:
    ids = [uuid7() for _ in range(50)]
    assert all(u.version == 7 for u in ids)
    assert all(u.variant == uuid.RFC_4122 for u in ids)
    # millisecond prefix is monotonic
    prefixes = [u.int >> 80 for u in ids]
    assert prefixes == sorted(prefixes)


def test_tracking_id_shape_and_check() -> None:
    tid = new_tracking_id("gj", year=2026)
    assert tid.startswith("SM-GJ-26-") and len(tid) == len("SM-GJ-26-K7Q2MX9")
    assert is_valid_tracking_id(tid)
    assert is_valid_tracking_id(tid.lower())


@given(st.text(alphabet=ALPHABET, min_size=6, max_size=6), st.integers(0, 6), st.sampled_from(ALPHABET))
def test_tracking_id_catches_every_single_char_typo(rand: str, pos: int, replacement: str) -> None:
    body = f"SM-RJ-26-{rand}"
    tid = body + luhn_mod_n_check_char(body)
    tail = list(tid[-7:])
    if tail[pos] == replacement:
        return
    tail[pos] = replacement
    assert not is_valid_tracking_id(tid[:-7] + "".join(tail))


def test_tracking_id_normalises_lookalikes() -> None:
    assert normalize_tracking_id(" sm-gj-26-k7q2mxo ") == "SM-GJ-26-K7Q2MX0"
    assert not is_valid_tracking_id("SM-GJ-26")
    assert not is_valid_tracking_id("XX-GJ-26-K7Q2MX9")


def test_field_encryption_round_trip_and_randomised() -> None:
    a, b = encrypt_str("Savitaben Rathwa"), encrypt_str("Savitaben Rathwa")
    assert a != b  # fresh data key + nonce per value
    assert decrypt_str(a) == "Savitaben Rathwa"
    assert encrypt_str(None) is None and decrypt_str(None) is None


def test_phone_normalisation_and_hash() -> None:
    assert normalize_phone("+91 98765-00001") == "9876500001"
    assert normalize_phone("09876500001") == "9876500001"
    assert phone_hash("+919876500001") == phone_hash("9876500001")
    assert keyed_hash("x", "a") != keyed_hash("x", "b")


def test_log_scrubbing() -> None:
    text = "call 9876500001 or +91 9876500002, aadhaar 2345 6789 0123, mail a.b@x.in"
    out = scrub_text(text)
    assert "9876500001" not in out and "6789" not in out and "a.b@x.in" not in out
    assert scrub({"full_name": "Ramesh", "income": 180000}) == {"full_name": "[REDACTED]", "income": 180000}


async def test_audit_chain_detects_tampering(session) -> None:  # type: ignore[no-untyped-def]
    for i in range(3):
        await audit.record(session, actor="admin:x", actor_role="admin", action="test.write", entity=f"t:{i}",
                           diff={"i": i, "phone": "9876500001"})
    await session.commit()
    report = await audit.verify_chain(session)
    assert report.ok and report.checked >= 3

    from sqlalchemy import select

    from app.db.models import AuditLog

    row = (await session.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1))).scalar_one()
    assert row.diff["phone"] == "[REDACTED]"

    from app.config import get_settings

    if not get_settings().is_sqlite:
        # Postgres refuses the tampering outright (append-only trigger).
        from sqlalchemy.exc import DBAPIError

        row.diff = {"i": 999}
        with pytest.raises(DBAPIError, match="append-only"):
            await session.commit()
        await session.rollback()
        return
    row.diff = {"i": 999}
    await session.commit()
    broken = await audit.verify_chain(session)
    assert not broken.ok and broken.broken_at_seq == row.seq
    await session.delete(row)
    await session.commit()


async def test_otp_login_and_lockout(client) -> None:  # type: ignore[no-untyped-def]
    headers = await login(client, "9876511111")
    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["role"] == "citizen"

    await client.post("/v1/auth/otp/request", json={"phone": "9876522222"})
    for _ in range(5):
        r = await client.post("/v1/auth/otp/verify", json={"phone": "9876522222", "code": "000001"})
    assert r.status_code == 401
    locked = await client.post("/v1/auth/otp/request", json={"phone": "9876522222"})
    assert locked.status_code == 429
    assert locked.json()["user_message_key"] == "errors.otp_locked"


async def test_rejects_bad_phone_and_token(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/v1/auth/otp/request", json={"phone": "1234567890"})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    r = await client.get("/v1/auth/me", headers={"authorization": "Bearer nope"})
    assert r.status_code == 401


async def test_system_status_labels_sandbox(client) -> None:  # type: ignore[no-untyped-def]
    body = (await client.get("/v1/system/status")).json()
    adapters = {a["name"]: a for a in body["adapters"]}
    assert adapters["sms"]["sandbox"] is True
    assert adapters["ranking_model"]["mode"] == "xgboost"  # trained model ships with the repo
    assert (await client.get("/healthz")).json() == {"status": "ok"}
