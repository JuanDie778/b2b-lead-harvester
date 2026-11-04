"""Test fixtures and offline DOM mocks for pytest suite."""
import asyncio
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
import pytest
from lead_harvester.core.models import CountryTarget, Lead, SearchPreset
from lead_harvester.storage.database import Database


class MockElementHandle:
    """Simulates Playwright's ElementHandle for offline DOM tests."""

    def __init__(
        self,
        text: str = "",
        attributes: Optional[Dict[str, str]] = None,
        children: Optional[Dict[str, "MockElementHandle"]] = None,
        is_visible: bool = True,
    ):
        self._text = text
        self._attributes = attributes or {}
        self._children = children or {}
        self._is_visible = is_visible

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> Optional[str]:
        return self._attributes.get(name)

    async def is_visible(self) -> bool:
        return self._is_visible

    async def query_selector(self, selector: str) -> Optional["MockElementHandle"]:
        return self._children.get(selector)

    async def query_selector_all(self, selector: str) -> List["MockElementHandle"]:
        child = self._children.get(selector)
        return [child] if child else []

    async def click(self) -> None:
        pass


class MockPage:
    """Simulates Playwright Page object."""

    def __init__(self, elements: Optional[Dict[str, MockElementHandle]] = None):
        self.elements = elements or {}
        self.url = "https://www.linkedin.com"
        self.closed = False

    async def goto(self, url: str, **kwargs) -> None:
        self.url = url

    async def wait_for_selector(self, selector: str, timeout: int = 5000) -> Optional[MockElementHandle]:
        if selector in self.elements:
            return self.elements[selector]
        return None

    async def query_selector(self, selector: str) -> Optional[MockElementHandle]:
        return self.elements.get(selector)

    async def query_selector_all(self, selector: str) -> List[MockElementHandle]:
        el = self.elements.get(selector)
        return [el] if el else []

    async def fill(self, selector: str, value: str) -> None:
        pass

    async def click(self, selector: str) -> None:
        pass

    async def evaluate(self, script: str) -> Any:
        return None

    async def wait_for_load_state(self, state: str) -> None:
        pass

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def temp_db(tmp_path: Path) -> Database:
    """Fixture providing an isolated temporary SQLite database."""
    db_file = tmp_path / "test_leads.db"
    return Database(db_file)


@pytest.fixture
def sample_lead() -> Lead:
    """Fixture providing a sample validated Lead object."""
    return Lead(
        author_name="John Doe",
        author_title="Senior BIM Manager | Revit & VDC Specialist",
        author_url="https://www.linkedin.com/in/johndoe-bim-12345",
        post_url="https://www.linkedin.com/feed/update/urn:li:activity:71234567890/",
        post_text="Excited to implement new BIM workflows on our new construction projects in London, UK!",
        post_date="2d",
        location="London, England, United Kingdom",
        search_term="BIM Manager",
        country="United Kingdom",
        scraped_date="2026-11-04 12:00:00",
    )


@pytest.fixture
def sample_preset_yaml(tmp_path: Path) -> Path:
    """Fixture creating a temporary preset YAML file."""
    content = """
name: "Test Preset"
description: "Preset for test environment"
search_terms:
  - "BIM Specialist"
  - "Revit Modeler"
countries:
  United States:
    code: "%5B%22urn%3Ali%3Afs_geo%3A103644278%22%5D"
    location_names: ["USA", "New York"]
    keywords: ["united states", "usa", "new york"]
  United Kingdom:
    code: "%5B%22urn%3Ali%3Afs_geo%3A101165590%22%5D"
    location_names: ["UK", "London"]
    keywords: ["uk", "united kingdom", "london"]
excluded_indicators:
  - "india"
  - "bangalore"
  - "mumbai"
undesired_languages:
  - "ar"
  - "hi"
max_posts_per_term: 10
max_pages: 2
max_posts_total: 20
"""
    yaml_file = tmp_path / "test_preset.yaml"
    yaml_file.write_text(content.strip(), encoding="utf-8")
    return yaml_file


@pytest.fixture
def mock_post_dom() -> MockElementHandle:
    """Fixture creating a realistic mock of LinkedIn post DOM tree."""
    actor_name = MockElementHandle(text="Jane Smith")
    actor_desc = MockElementHandle(text="VDC Engineer at Tech AEC Solutions")
    actor_link = MockElementHandle(
        attributes={"href": "https://www.linkedin.com/in/janesmith-vdc?trk=public"}
    )
    post_link = MockElementHandle(
        attributes={"href": "https://www.linkedin.com/feed/update/urn:li:activity:998877665544/"}
    )
    post_text = MockElementHandle(
        text="Looking for a talented Revit Modeler to join our team in New York, USA! #BIM #Hiring"
    )
    post_date = MockElementHandle(text="1w • Edited")
    distance_el = MockElementHandle(text="New York, NY")

    children = {
        ".update-components-actor__name": actor_name,
        ".update-components-actor__description": actor_desc,
        'a.app-aware-link[href*="/in/"]': actor_link,
        'a.app-aware-link[href*="/feed/update/"]': post_link,
        ".update-components-text": post_text,
        ".update-components-actor__sub-description": post_date,
        ".update-components-actor__sub-description .update-components-actor__distance": distance_el,
    }

    return MockElementHandle(children=children)
