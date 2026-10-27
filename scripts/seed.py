"""Load the fictional demo company, Brightline Electricals (idempotent).

    make seed

Its profile (seed/brightline/profile.json) carries the three traps: papers worded "Trading
Business", no BIS licence, and turnover just under a common threshold. Fictional data only.
"""

import asyncio
import sys

from greenink.core.settings import get_settings
from greenink.db.seed import seed_demo
from greenink.db.session import make_engine, make_sessionmaker


async def main() -> int:
    engine = make_engine(get_settings().database_url)
    try:
        company = await seed_demo(make_sessionmaker(engine))
    finally:
        await engine.dispose()
    print(f"Seeded demo company {company.name} ({company.id})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
