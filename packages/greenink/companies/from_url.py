"""Draft company profile from a website: Tavily Extract, then the `profile_url` task."""

from pydantic import SecretStr

from greenink.core.models import CompanyProfile
from greenink.llm.port import LLM


class TavilyProfileBuilder:
    def __init__(self, llm: LLM, tavily_api_key: SecretStr) -> None:
        self._llm = llm
        self._tavily_api_key = tavily_api_key

    async def from_url(self, url: str) -> CompanyProfile:
        raise NotImplementedError("TODO(lane-A): Tavily Extract + Lightning -> CompanyProfile")
