"""Unit tests for NLP LanguageFilter and GeoValidator modules."""
import pytest
from lead_harvester.core.models import CountryTarget
from lead_harvester.nlp.geo_validator import GeoValidator
from lead_harvester.nlp.lang_filter import LanguageFilter


class TestLanguageFilter:
    """Test suite for language classification and rejection."""

    def test_english_accepted(self):
        flt = LanguageFilter()
        text = "We are seeking a senior BIM coordinator for immediate hiring in our London headquarters."
        assert flt.is_accepted(text) is True

    def test_spanish_accepted(self):
        flt = LanguageFilter()
        text = "Estamos buscando un modelador Revit con experiencia en proyectos de edificación en Madrid."
        assert flt.is_accepted(text) is True

    def test_arabic_rejected(self):
        flt = LanguageFilter()
        text = "مطلوب مهندس بي آي إم للعمل فورا في مشروع جديد"
        assert flt.is_accepted(text) is False

    def test_hindi_rejected(self):
        flt = LanguageFilter()
        text = "हमें तुरंत बीआईएम मॉडलर की आवश्यकता है हमारे नए प्रोजेक्ट के लिए"
        assert flt.is_accepted(text) is False

    def test_bengali_rejected(self):
        flt = LanguageFilter()
        text = "আমাদের নতুন প্রকল্পের জন্য একজন দক্ষ প্রকৌশলী প্রয়োজন"
        assert flt.is_accepted(text) is False

    def test_na_and_empty_text_accepted(self):
        flt = LanguageFilter()
        assert flt.is_accepted("N/A") is True
        assert flt.is_accepted("") is True
        assert flt.is_accepted(None) is True

    def test_custom_undesired_languages(self):
        flt = LanguageFilter(undesired_languages=["fr"])
        fr_text = "Nous recherchons un ingénieur BIM expérimenté pour nos chantiers."
        assert flt.is_accepted(fr_text) is False


class TestGeoValidator:
    """Test suite for geographic validation and regional exclusion."""

    @pytest.fixture
    def validator(self) -> GeoValidator:
        return GeoValidator()

    @pytest.fixture
    def us_target(self) -> CountryTarget:
        return CountryTarget(
            code="103644278",
            location_names=["USA", "United States"],
            keywords=["united states", "usa", "us", "new york", "california", "texas"],
        )

    @pytest.fixture
    def canada_target(self) -> CountryTarget:
        return CountryTarget(
            code="101174742",
            location_names=["Canada", "Canadá"],
            keywords=["canada", "canadá", "toronto", "vancouver", "montreal"],
        )

    def test_emoji_flag_immediately_excluded(self, validator):
        assert validator.is_excluded("Top BIM services available 🇮🇳") is True

    def test_explicit_phrase_immediately_excluded(self, validator):
        assert validator.is_excluded("Our firm is based in India with offshore delivery") is True
        assert validator.is_excluded("Located in India for low cost modeling") is True

    def test_threshold_multiple_indicators_excluded(self, validator):
        # 2 indicators: "india" and "bangalore"
        assert validator.is_excluded("Best architecture modeling team in Bangalore, India") is True

    def test_single_subindicator_not_falsely_excluded(self, validator):
        # Indianapolis should NOT be falsely excluded
        assert validator.is_excluded("We are hosting an AEC conference in Indianapolis next week") is False

    def test_verify_content_valid_us(self, validator, us_target):
        content = "We have an open role for a Revit specialist in New York office."
        assert validator.verify_content(content, country="United States", country_target=us_target) is True

    def test_verify_content_short_token_boundary(self, validator, us_target):
        # "focus" or "status" or "industry" must NOT trigger the "us" keyword
        false_content = "Focus on continuous industry growth and project status updates."
        assert validator.verify_content(false_content, country="United States", country_target=us_target) is False

    def test_verify_content_negative_country(self, validator, us_target):
        content = "Hiring architecture specialists in Tokyo, Japan for upcoming towers."
        assert validator.verify_content(content, country="United States", country_target=us_target) is False

    def test_verify_content_excluded_overrides_valid_keyword(self, validator, us_target):
        # Even if "new york" is mentioned, presence of India indicators excludes the lead
        content = "Providing BIM services to New York clients from our Bangalore, India center 🇮🇳"
        assert validator.verify_content(content, country="United States", country_target=us_target) is False

    def test_verify_location_string(self, validator, canada_target):
        assert validator.verify_location_string("Toronto, Ontario, Canada", "Canada", canada_target) is True
        assert validator.verify_location_string("Mumbai, Maharashtra, India", "Canada", canada_target) is False
        assert validator.verify_location_string("N/A", "Canada", canada_target) is False
        assert validator.verify_location_string(None, "Canada", canada_target) is False
