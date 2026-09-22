"""Background work for applications (runs inline locally, on ARQ workers in compose)."""

import asyncio
from uuid import UUID

from app.core.jobs import job
from app.core.storage import get_storage
from app.db.models import Applicant, Application
from app.db.session import get_sessionmaker


async def render_and_store(application_id: str) -> str:
    from app.modules.applications import service
    from app.modules.applications.pdf import render_loan_file

    async with get_sessionmaker()() as session:
        app = await session.get(Application, UUID(application_id))
        if app is None:
            return "missing"
        applicant = await session.get(Applicant, app.applicant_id)
        assert applicant is not None
        view = await service.loan_file_view(session, app, applicant)
        storage = get_storage()
        qr = await storage.get(f"applications/{app.id}/qr.png")
        pdf = await asyncio.to_thread(render_loan_file, view, qr)
        key = f"applications/{app.id}/loan-file.pdf"
        await storage.put(key, pdf)
        await session.commit()
        return key


@job("render_loan_file")
async def render_loan_file_job(application_id: str) -> str:
    return await render_and_store(application_id)
