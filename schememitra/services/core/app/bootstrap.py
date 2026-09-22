"""Startup: signing keys, runtime flags, warm models. Schema is managed by Alembic
(`alembic upgrade head`), which `make dev`/`make seed` run before the server starts."""

from app.logging import get_logger

log = get_logger("bootstrap")


async def startup() -> None:
    from app.core.flags import load_flags
    from app.core.keys import ensure_qr_signing_key
    from app.modules.ranking.service import warm as warm_ranker

    ensure_qr_signing_key()
    await load_flags()
    warm_ranker()
    log.info("core ready")
