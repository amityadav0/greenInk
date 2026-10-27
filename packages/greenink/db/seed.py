"""The shared, read-only demo company (fictional Brightline Electricals). Idempotent."""

import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from greenink.core.enums import CompanySource, VerifiedLevel
from greenink.core.models import Company, CompanyProfile
from greenink.db import repos

DEMO_COMPANY_ID = UUID("6b1f3c1e-9d2a-4c55-8e7b-0b9a1d2c3e4f")
DEMO_PROFILE = Path(__file__).resolve().parents[3] / "seed" / "brightline" / "profile.json"


async def seed_demo(sessions: async_sessionmaker[AsyncSession], profile_path: Path = DEMO_PROFILE) -> Company:
    profile = CompanyProfile.model_validate_json(await asyncio.to_thread(profile_path.read_text, "utf-8"))
    async with sessions.begin() as session:
        return await repos.save_company(
            session,
            company_id=DEMO_COMPANY_ID,
            name=profile.legal_name,
            profile=profile,
            source=CompanySource.DEMO,
            verified_level=VerifiedLevel.DOCUMENTED,
            session_id=None,
        )
