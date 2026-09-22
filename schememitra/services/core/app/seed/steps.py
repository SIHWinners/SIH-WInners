"""Seed steps in dependency order. Each step is idempotent."""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.seed.demo_documents import seed_demo_documents
from app.seed.partners import seed_partners
from app.seed.schemes import seed_schemes
from app.seed.users import seed_users

Step = Callable[[AsyncSession], Awaitable[str]]

ORDER: list[tuple[str, Step]] = [
    ("schemes", seed_schemes),
    ("partners", seed_partners),
    ("users", seed_users),
    ("demo documents", seed_demo_documents),
]
