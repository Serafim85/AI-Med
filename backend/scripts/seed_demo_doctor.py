"""Seed a single demo doctor. Idempotent: re-running is safe.

Run:
    docker compose exec backend python -m scripts.seed_demo_doctor
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User

DEMO_EMAIL = "demo@clinic.local"
DEMO_PASSWORD = "demo1234"
DEMO_FULL_NAME = "Демо Врач"

logger = logging.getLogger("scripts.seed_demo_doctor")


async def _seed() -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User).where(User.email == DEMO_EMAIL))
        user = existing.scalar_one_or_none()
        if user is not None:
            logger.info("Демо-врач уже существует (id=%s), пропускаем.", user.id)
            print(f"Демо-врач уже существует: {user.email}")
            return

        user = User(
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            full_name=DEMO_FULL_NAME,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("Создан демо-врач id=%s email=%s", user.id, user.email)
        print(f"Создан демо-врач: {user.email} / {DEMO_PASSWORD}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
