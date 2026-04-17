"""Auth endpoint integration tests.

Covers:
* POST /api/v1/auth/login — success (returns token + user, writes audit log)
* POST /api/v1/auth/login — invalid password (returns 401, no audit log)
* GET /api/v1/auth/me — with and without token
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.user import User

DEMO_EMAIL = "demo@clinic.local"
DEMO_PASSWORD = "demo1234"
DEMO_FULL_NAME = "Демо Врач"


@pytest_asyncio.fixture
async def seeded_user(db_session) -> User:
    user = User(
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=DEMO_FULL_NAME,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_login_success(client, db_session, seeded_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert body["user"]["email"] == DEMO_EMAIL
    assert body["user"]["full_name"] == DEMO_FULL_NAME
    assert body["user"]["id"] == str(seeded_user.id)

    audit_rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert any(row.action == "login" and row.user_id == seeded_user.id for row in audit_rows)


async def test_login_invalid_password(client, db_session, seeded_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": "wrong-password"},
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Неверные учётные данные"}

    audit_rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert all(row.action != "login" for row in audit_rows)


async def test_login_unknown_email(client, seeded_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "no-such@clinic.local", "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Неверные учётные данные"}


async def test_me_without_token(client, seeded_user):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_token(client, seeded_user):
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == DEMO_EMAIL
    assert body["full_name"] == DEMO_FULL_NAME
