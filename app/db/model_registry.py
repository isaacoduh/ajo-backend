"""Centralized model imports for SQLAlchemy metadata discovery."""


def import_all_models() -> None:
    """Import every module that defines SQLAlchemy models.

    Alembic autogenerate calls this before reading `Base.metadata`. Future
    feature passes should add their model modules here when tables are created.
    """
    from app.modules.identity import models as identity_models
    from app.modules.ledger import models as ledger_models
    from app.modules.members import models as members_models
    from app.modules.payments import models as payments_models
    from app.modules.screening import models as screening_models
    from app.modules.wallets import models as wallets_models
    from app.workers import models as worker_models

    _ = (
        identity_models,
        ledger_models,
        members_models,
        payments_models,
        screening_models,
        wallets_models,
        worker_models,
    )
