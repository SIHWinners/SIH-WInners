"""`python -m app.seed` — loads demo data. Idempotent: re-running updates in place.

All people, partners and applications created here are fictional demo data."""

import asyncio
import sys
from pathlib import Path

from app.config import CORE_DIR
from app.db.session import dispose_engine, get_sessionmaker
from app.logging import configure_logging, get_logger
from app.seed import steps

log = get_logger("seed")


async def main() -> None:
    configure_logging("INFO")
    async with get_sessionmaker()() as session:
        for name, step in steps.ORDER:
            result = await step(session)
            await session.commit()
            print(f"  ✓ {name}: {result}")
    await dispose_engine()
    marker = CORE_DIR / "var" / ".seeded"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"Seeding demo data into {Path(CORE_DIR, 'var')} …")
    asyncio.run(main())
