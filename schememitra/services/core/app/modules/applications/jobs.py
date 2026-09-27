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
        # Rendering is read-only: roll back so this job can never write application state
        # (it runs inline in the local profile, concurrently with the submitting request).
        await session.rollback()
        return key


@job("render_loan_file")
async def render_loan_file_job(application_id: str) -> str:
    return await render_and_store(application_id)
