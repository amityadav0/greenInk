"""The citation verifier: no requirement reaches the judge or the UI unless it passes."""

from greenink.core.models import Requirement
from greenink.docs.port import Pages

MATCH_THRESHOLD = 90
"""Minimum rapidfuzz `partial_ratio` between a quote and its cited page."""


class FuzzyQuoteVerifier:
    def verify(self, requirements: list[Requirement], pages: Pages) -> list[Requirement]:
        raise NotImplementedError("TODO(lane-A): rapidfuzz partial_ratio >= MATCH_THRESHOLD")
