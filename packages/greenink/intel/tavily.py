"""Price intel from Tavily Search + Extract, called at runtime."""

from uuid import UUID

from pydantic import SecretStr

from greenink.core.models import PriceIntel


class TavilyIntelProvider:
    def __init__(self, api_key: SecretStr) -> None:
        self._api_key = api_key

    async def prices(self, analysis_id: UUID, item: str, buyer: str | None) -> PriceIntel:
        raise NotImplementedError("TODO(lane-A): Tavily Search + Extract -> cited price band")
