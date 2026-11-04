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
        Requires >= threshold matches to prevent false positives (e.g. Indianapolis).
        Direct flag indicators like flags or explicit 'based in india' count as immediate match.
        """
        if not text or text == "N/A":
            return False

        text_lower = text.lower()
        active_indicators = indicators if indicators is not None else self.excluded_indicators

        # Immediate single-hit indicators
        if "🇮🇳" in text or "based in india" in text_lower or "located in india" in text_lower:
            return True

        hits = 0
        for indicator in active_indicators:
            # Skip checking "india" substring match inside "indianapolis"
            if indicator == "india" and "indianapolis" in text_lower and text_lower.count("india") == 1:
                continue

            if indicator in text_lower:
                hits += 1
                if hits >= threshold:
                    return True

        return False

    @staticmethod
    def _matches_keyword(text_lower: str, keyword: str) -> bool:
        """Match keyword, applying word boundary for short abbreviations."""
        kw_clean = keyword.lower().strip()
        if not kw_clean:
            return False
            
        if len(kw_clean) <= 3:
            # Word boundary regex for short codes like "us", "uk", "co"
            pattern = rf"\b{re.escape(kw_clean)}\b"
            return bool(re.search(pattern, text_lower))
        return kw_clean in text_lower

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
