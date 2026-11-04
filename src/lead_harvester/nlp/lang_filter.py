"""Language detection and filtering using langid with regex fallback."""
import re
from typing import List, Optional
try:
    import langid
except ImportError:
    langid = None  # Handled with graceful fallback


class LanguageFilter:
    """Classifies text languages and filters out undesired idioms."""

    DEFAULT_UNDESIRED = ["ar", "hi", "ur", "bn", "pa"]

    # Unicode ranges for non-target scripts
    ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
    DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")
    BENGALI_PATTERN = re.compile(r"[\u0980-\u09FF]")
    GURMUKHI_PATTERN = re.compile(r"[\u0A00-\u0A7F]")

    def __init__(self, undesired_languages: Optional[List[str]] = None):
        self.undesired_languages = (
            [lang.lower() for lang in undesired_languages]
            if undesired_languages is not None
            else self.DEFAULT_UNDESIRED
        )

    def detect_language(self, text: Optional[str]) -> str:
        """Detect language of text. Returns ISO language code or 'unknown'."""
        if not text or text == "N/A" or len(text.strip()) < 10:
            return "unknown"

        # Regex pre-checks for distinct scripts
        if self.ARABIC_PATTERN.search(text):
            return "ar"
        if self.DEVANAGARI_PATTERN.search(text):
            return "hi"
        if self.BENGALI_PATTERN.search(text):
            return "bn"
        if self.GURMUKHI_PATTERN.search(text):
            return "pa"

        if langid is not None:
            try:
                lang, _confidence = langid.classify(text)
                return str(lang)
            except Exception:
                pass

        return "unknown"

    def is_accepted(self, text: Optional[str], undesired_override: Optional[List[str]] = None) -> bool:
        """Return True if text language is permitted; False if in undesired list."""
        if not text or text == "N/A":
            return True

        undesired = (
            [lang.lower() for lang in undesired_override]
            if undesired_override is not None
            else self.undesired_languages
        )

        detected = self.detect_language(text)

        if detected in undesired:
            return False

        if detected == "unknown":
            # Fallback script checks
            if self.ARABIC_PATTERN.search(text) and "ar" in undesired:
                return False
            if self.DEVANAGARI_PATTERN.search(text) and "hi" in undesired:
                return False
            if self.BENGALI_PATTERN.search(text) and "bn" in undesired:
                return False
            if self.GURMUKHI_PATTERN.search(text) and "pa" in undesired:
                return False

        return True
