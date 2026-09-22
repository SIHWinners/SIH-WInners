from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Scheme, SchemeRuleVersion
from app.modules.eligibility.loader import invalidate_ruleset, load_rule_files


async def seed_schemes(session: AsyncSession) -> str:
    docs = load_rule_files()
    for doc in docs:
        scheme = (await session.execute(select(Scheme).where(Scheme.code == doc["scheme_code"]))).scalar_one_or_none()
        if scheme is None:
            scheme = Scheme(code=doc["scheme_code"], apex_corp=doc["apex_corp"], name_i18n=doc["name"],
                            loan_type=doc["loan_type"], active=True)
            session.add(scheme)
            await session.flush()
        scheme.name_i18n, scheme.loan_type, scheme.apex_corp = doc["name"], doc["loan_type"], doc["apex_corp"]
        version = (
            await session.execute(
                select(SchemeRuleVersion).where(
                    SchemeRuleVersion.scheme_id == scheme.id, SchemeRuleVersion.version == doc["version"]
                )
            )
        ).scalar_one_or_none()
        if version is None:
            version = SchemeRuleVersion(scheme_id=scheme.id, version=doc["version"], author="seed",
                                        approved_by="seed", status="published",
                                        effective_from=date.fromisoformat(doc.get("effective_from", "2026-04-01")),
                                        source_url=doc["source_url"], rules=doc)
            session.add(version)
        version.rules = doc
        version.params = doc["params"]
        version.source_url = doc["source_url"]
        version.verified_on = date.fromisoformat(doc["verified_on"]) if doc.get("verified_on") else None
        await session.flush()
        scheme.rule_version_id = version.id
    invalidate_ruleset()
    return f"{len(docs)} schemes"
