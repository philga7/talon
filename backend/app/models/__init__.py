"""SQLAlchemy ORM models."""

from sqlalchemy.orm import DeclarativeBase

# pyright: reportUnknownVariableType=false, reportUntypedBaseClass=false


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass
