"""Geographic validation, target location matching, and exclusion filtering."""
import re
from typing import Dict, List, Optional
from ..core.models import CountryTarget


class GeoValidator:
    """Validates geographic relevance of leads and filters out non-target locations."""

    DEFAULT_EXCLUSIONS = [
        "india", "indian", "bangalore", "mumbai", "delhi", "chennai",
        "hyderabad", "kolkata", "pune", "bengaluru", "noida", "gurgaon",
        "ahmedabad", "india's", "from india", "based in india", "located in india",
        "bombay", "madras", "calcutta", "new delhi", "india based", "working in india",
        "🇮🇳"
    ]

    def __init__(self, excluded_indicators: Optional[List[str]] = None):
        self.excluded_indicators = (
            [ind.lower() for ind in excluded_indicators]
            if excluded_indicators is not None
            else self.DEFAULT_EXCLUSIONS
        )

    def is_excluded(
        self,
        text: Optional[str],
        indicators: Optional[List[str]] = None,
        threshold: int = 2
    ) -> bool:
        """
        Check if text contains strong indications of excluded regions.
        Requires >= threshold distinct matches to prevent false positives (e.g. Indiana, Indian cuisine).
        Direct flag indicators (🇮🇳) or explicit 'based in india' count as immediate match.
        """
        if not text or text == "N/A":
            return False

        # 1. Immediate flag match
        if "🇮🇳" in text:
            return True

        text_lower = text.lower()

        # 2. Immediate unambiguous phrases
        immediate_phrases = [
            "based in india",
            "located in india",
            "from india",
            "india based",
            "working in india",
        ]
        for phrase in immediate_phrases:
            phrase_pat = rf"(?:(?<=\W)|^){re.escape(phrase)}(?:(?=\W)|$)"
            if re.search(phrase_pat, text_lower):
                return True

        # 3. Threshold matching with boundary check & non-overlapping spans
        active_indicators = (
            [ind.lower() for ind in indicators]
            if indicators is not None
            else self.excluded_indicators
        )

        # Sort descending by length so longer phrases match before subphrases
        sorted_ind = sorted(
            [i for i in active_indicators if i != "🇮🇳" and i not in immediate_phrases],
            key=len,
            reverse=True,
        )

        matched_spans = []
        hits = 0
        for ind in sorted_ind:
            pattern = rf"(?:(?<=\W)|^){re.escape(ind)}(?:(?=\W)|$)"
            for m in re.finditer(pattern, text_lower):
                start, end = m.span()
                # Do not count if this span overlaps with an already matched longer indicator
                if not any(s <= start and end <= e for s, e in matched_spans):
                    matched_spans.append((start, end))
                    hits += 1
                    if hits >= threshold:
                        return True

        return False

    @staticmethod
    def _matches_keyword(text_lower: str, keyword: str) -> bool:
        """Match keyword with robust word boundaries to prevent substring collisions."""
        kw_clean = keyword.lower().strip()
        if not kw_clean:
            return False

        # Boundary-safe regex matching for both word characters and punctuation (e.g. "u.s.")
        pattern = rf"(?:(?<=\W)|^){re.escape(kw_clean)}(?:(?=\W)|$)"
        return bool(re.search(pattern, text_lower))

    def verify_content(
        self,
        text: Optional[str],
        country: str,
        country_target: Optional[CountryTarget] = None,
        keywords_override: Optional[List[str]] = None
    ) -> bool:
        """Verify if text content matches target country and is not excluded."""
        if not text or text == "N/A":
            return False

        if self.is_excluded(text):
            return False

        text_lower = text.lower()

        keywords: List[str] = []
        if keywords_override:
            keywords.extend(keywords_override)
        elif country_target:
            keywords.extend(country_target.keywords)
            keywords.extend(country_target.location_names)
        else:
            keywords.append(country.lower())

        return any(self._matches_keyword(text_lower, kw) for kw in keywords)

    def verify_location_string(
        self,
        location: Optional[str],
        country: str,
        country_target: Optional[CountryTarget] = None,
        keywords_override: Optional[List[str]] = None
    ) -> bool:
        """Verify explicit location string from author profile or post tag."""
        if not location or location == "N/A":
            return False

        return self.verify_content(
            text=location,
            country=country,
            country_target=country_target,
            keywords_override=keywords_override
        )
