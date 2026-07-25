"""
SQLAlchemy declarative base model.
Tüm ORM modelleri buradan türer.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Abstract base model."""
    pass
