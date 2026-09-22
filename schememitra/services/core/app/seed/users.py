"""Demo accounts, one per role (all fictional). Phone numbers are in the 9000000xxx range so
they can never collide with a real subscriber in a demo."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import phone_hash
from app.db.models import Partner, User


@dataclass(frozen=True)
class DemoUser:
    phone: str
    role: str
    display_name: str | None = None
    lang: str = "en"
    partner_name_prefix: str | None = None
    csc_id: str | None = None


DEMO_USERS = [
    DemoUser("9000000001", "citizen", lang="gu"),  # Savitaben
    DemoUser("9000000002", "citizen", lang="hi"),  # Ramesh
    DemoUser("9000000003", "citizen", lang="ta"),  # Kavya
    DemoUser("9000000004", "citizen", lang="ur"),  # Imran
    DemoUser("9000000005", "citizen", lang="hi"),  # edge persona
    DemoUser("9000000010", "csc_operator", "Anil Verma (CSC Lucknow — demo)", "hi", csc_id="CSC-UP-LKO-0142"),
    DemoUser("9000000011", "csc_operator", "Meena Patel (CSC Dahod — demo)", "gu", csc_id="CSC-GJ-DAH-0031"),
    DemoUser("9000000020", "partner_officer", "Officer, Dahod SCA (demo)", "gu", partner_name_prefix="Dahod District SCA"),
    DemoUser("9000000021", "partner_officer", "Officer, Barmer SCA (demo)", "hi", partner_name_prefix="Barmer District SCA"),
    DemoUser("9000000022", "partner_officer", "Officer, Madurai SCA (demo)", "ta", partner_name_prefix="Madurai District SCA"),
    DemoUser("9000000023", "partner_officer", "Officer, Lucknow SCA (demo)", "hi", partner_name_prefix="Lucknow District SCA"),
    DemoUser("9000000030", "admin", "Platform admin (demo)", "en"),
    DemoUser("9000000040", "policy_viewer", "MoSJE policy desk (demo)", "en"),
]


async def seed_users(session: AsyncSession) -> str:
    created = 0
    for demo in DEMO_USERS:
        partner_id = None
        if demo.partner_name_prefix:
            partner_id = (
                await session.execute(
                    select(Partner.id).where(Partner.name.startswith(demo.partner_name_prefix)).limit(1)
                )
            ).scalar_one_or_none()
        user = (await session.execute(select(User).where(User.phone_hash == phone_hash(demo.phone)))).scalar_one_or_none()
        if user is None:
            user = User(phone_hash=phone_hash(demo.phone), phone_enc=demo.phone, role=demo.role)
            session.add(user)
            created += 1
        user.role = demo.role
        user.display_name = demo.display_name
        user.preferred_lang = demo.lang
        user.partner_id = partner_id
        user.csc_id = demo.csc_id
    return f"{len(DEMO_USERS)} demo users ({created} new)"
