"""Database initialization and migration utilities for MSS backend."""

__all__ = ['init_db']


def init_db(db_path=None):
    """Initialize the database. See db.init_db module for details."""
    from .init_db import init_db as _init_db
    return _init_db(db_path)
