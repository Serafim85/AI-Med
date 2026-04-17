"""Pytest fixtures: in-memory SQLite async engine + FastAPI app with DI override.

We deliberately use SQLite (via aiosqlite) for tests so the suite does not
depend on a running Postgres instance. Types used in the production models
(``sa.Uuid``, ``sa.Enum``, ``sa.JSON.with_variant(JSONB, "postgresql")``) are
dialect-neutral and round-trip correctly on SQLite.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Settings read JWT_SECRET at import time; set it before importing the app.
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Import the application AFTER env is wired.
# NB: ``import app.models`` rebinds the name ``app`` in this module to the
# package, so it must come BEFORE ``from app.main import app`` (which binds
# ``app`` to the FastAPI instance).
import app.models  # noqa: E402,F401  -- ensure all models are registered
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(test_engine):
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.pop(get_db, None)


# pytest-asyncio: anyio is not used, mark all tests as asyncio.
@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


DEMO_EMAIL = "demo@clinic.local"
DEMO_PASSWORD = "demo1234"
DEMO_FULL_NAME = "Демо Врач"


@pytest_asyncio.fixture
async def demo_doctor(db_session) -> User:
    """Demo doctor user persisted in the test DB."""
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


@pytest_asyncio.fixture
async def auth_headers(client, demo_doctor) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
