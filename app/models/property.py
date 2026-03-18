"""SQLAlchemy declarative base; all ORM models inherit from Base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all app models (property, user, etc.)."""
    pass
