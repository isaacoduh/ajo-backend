"""Centralized model imports for SQLAlchemy metadata discovery."""


def import_all_models() -> None:
    """Import every module that defines SQLAlchemy models.

    Alembic autogenerate calls this before reading `Base.metadata`. Future
    feature passes should add their model modules here when tables are created.
    """

