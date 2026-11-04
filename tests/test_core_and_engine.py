"""Unit tests for models, presets, and engine scraping components."""
from pathlib import Path
import pytest
from lead_harvester.core.models import ExecutionStats, Lead, SearchPreset
from lead_harvester.engine.auth import LinkedInAuth
from lead_harvester.engine.scraper import LeadScraper
from lead_harvester.storage.database import Database
from .conftest import MockElementHandle, MockPage


class TestCoreModelsAndPresets:
    """Test suite for domain models and YAML configuration presets."""

    def test_load_sample_preset(self, sample_preset_yaml: Path):
        preset = SearchPreset.load_from_yaml(sample_preset_yaml)
        assert preset.name == "Test Preset"
        assert len(preset.search_terms) == 2
        assert "United States" in preset.countries
        assert "United Kingdom" in preset.countries
        assert "india" in preset.excluded_indicators

    def test_load_real_bim_preset(self):
        preset_path = Path("config/presets/bim_aec.yaml")
        if not preset_path.exists():
            # Resolve relative to project root
            preset_path = Path(__file__).resolve().parent.parent / "config" / "presets" / "bim_aec.yaml"
        preset = SearchPreset.load_from_yaml(preset_path)
        assert "BIM" in preset.name
        assert len(preset.search_terms) >= 10
        assert "United States" in preset.countries

    def test_load_real_tech_preset(self):
        preset_path = Path("config/presets/tech_startups.yaml")
        if not preset_path.exists():
            preset_path = Path(__file__).resolve().parent.parent / "config" / "presets" / "tech_startups.yaml"
        preset = SearchPreset.load_from_yaml(preset_path)
        assert "Tech" in preset.name
        assert "Founder & CEO" in preset.search_terms

    def test_lead_model_defaults_and_hash(self):
        lead = Lead(
            author_url="https://linkedin.com/in/test-engineer",
            post_url="https://linkedin.com/feed/update/999",
        )
        assert lead.hash_id != ""
        assert len(lead.hash_id) == 64
        assert lead.author_name == "N/A"
        assert lead.scraped_date != ""

    def test_execution_stats_telemetry(self):
        stats = ExecutionStats()
        stats.record_country("Canada", 2)
        stats.record_country("Canada", 1)
        stats.record_term("BIM Manager", 3)

        assert stats.countries_processed["Canada"] == 3
        assert stats.terms_processed["BIM Manager"] == 3


class TestScraperEngineUnit:
    """Test suite for DOM extraction using mock Playwright elements."""

    @pytest.mark.asyncio
    async def test_extract_post_data_from_mock_dom(
        self,
        mock_post_dom: MockElementHandle,
        temp_db: Database,
        sample_preset_yaml: Path,
    ):
        preset = SearchPreset.load_from_yaml(sample_preset_yaml)
        scraper = LeadScraper(preset=preset, database=temp_db)

        data = await scraper.extract_post_data(mock_post_dom)

        assert data["author_name"] == "Jane Smith"
        assert data["author_title"] == "VDC Engineer at Tech AEC Solutions"
        assert data["author_url"] == "https://www.linkedin.com/in/janesmith-vdc"
        assert data["post_url"] == "https://www.linkedin.com/feed/update/urn:li:activity:998877665544/"
        assert "Revit Modeler" in data["post_text"]
        assert data["post_date"] == "1w"
        assert data["location"] == "New York, NY"

    def test_extract_activity_id(self):
        urn = "urn:li:activity:712398472938479238"
        url = LeadScraper._extract_activity_id(urn)
        assert url == "https://www.linkedin.com/feed/update/712398472938479238/"

        ugc_urn = "urn:li:ugcPost:712398472938479238"
        ugc_url = LeadScraper._extract_activity_id(ugc_urn)
        assert ugc_url == "https://www.linkedin.com/feed/update/712398472938479238/"

        invalid_urn = "urn:li:fs_miniProfile:someid"
        assert LeadScraper._extract_activity_id(invalid_urn) is None

    @pytest.mark.asyncio
    async def test_extract_post_data_root_data_urn(
        self,
        temp_db: Database,
        sample_preset_yaml: Path,
    ):
        preset = SearchPreset.load_from_yaml(sample_preset_yaml)
        scraper = LeadScraper(preset=preset, database=temp_db)

        # Root element itself has data-urn attribute (common in LinkedIn DOM)
        root_post = MockElementHandle(
            attributes={"data-urn": "urn:li:activity:554433221100"},
            children={
                ".update-components-actor__name": MockElementHandle(text="Alice Architect"),
                ".update-components-actor__description": MockElementHandle(text="BIM Director"),
                ".update-components-text": MockElementHandle(text="Exciting new BIM project in London!"),
            },
        )

        data = await scraper.extract_post_data(root_post)
        assert data["author_name"] == "Alice Architect"
        assert data["post_url"] == "https://www.linkedin.com/feed/update/554433221100/"

    @pytest.mark.asyncio
    async def test_auth_dismiss_popups(self):
        dismiss_btn = MockElementHandle(is_visible=True)
        page = MockPage(elements={".artdeco-modal__dismiss": dismiss_btn})
        # Should execute without error
        await LinkedInAuth.dismiss_popups(page)
