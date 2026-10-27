"""The citation verifier: no requirement reaches the judge or the UI unless it passes.

A requirement is verified when its quote fuzzy-matches the text of the page it cites
(rapidfuzz partial_ratio >= MATCH_THRESHOLD after normalisation).
"""

import re
import unicodedata

from rapidfuzz import fuzz

from greenink.core.models import Requirement
from greenink.docs.port import Pages

MATCH_THRESHOLD = 90
"""Minimum rapidfuzz `partial_ratio` between a quote and its cited page."""
MIN_QUOTE_CHARS = 12
"""Shorter quotes ("No", "1 Year (s)") match almost any page, so they prove nothing."""

_SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Compatibility forms, one space for any whitespace run (labels and values sit on
    separate lines in GeM PDFs), lower case."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip().lower()


def quote_score(quote: str, page_text: str) -> float:
    needle, haystack = normalise(quote), normalise(page_text)
    if len(needle) < MIN_QUOTE_CHARS or not haystack:
        return 0.0
    if needle in haystack:
        return 100.0
    return float(fuzz.partial_ratio(needle, haystack))


class FuzzyQuoteVerifier:
    def verify(self, requirements: list[Requirement], pages: Pages) -> list[Requirement]:
        by_page = {page.page_no: page.text for page in pages}
        return [
            requirement.model_copy(
                update={
                    "verified": quote_score(requirement.quote, by_page.get(requirement.page_no, ""))
                    >= MATCH_THRESHOLD
                }
            )
            for requirement in requirements
        ]
