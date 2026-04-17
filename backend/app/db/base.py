from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    Models will be added in later steps; kept here so Alembic can import
    a stable metadata object.
    """
