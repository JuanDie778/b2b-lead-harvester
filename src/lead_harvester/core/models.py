"""Data models and entities for B2B Lead Harvester."""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field, model_validator


class CountryTarget(BaseModel):
    """Geographic search target configuration."""
    code: str = Field(..., description="LinkedIn URL facetGeoRegion encoded URN")
    location_names: List[str] = Field(default_factory=list, description="Target location aliases")
    keywords: List[str] = Field(default_factory=list, description="Keywords indicating presence in this region")


class SearchPreset(BaseModel):
    """Domain preset defining search terms, geolocations, and filtering rules."""
    name: str = Field(..., description="Preset name")
    description: str = Field(default="", description="Preset description")
    search_terms: List[str] = Field(default_factory=list, description="Job titles or query terms")
    countries: Dict[str, CountryTarget] = Field(default_factory=dict, description="Target countries")
    excluded_indicators: List[str] = Field(default_factory=list, description="Phrases/tokens to filter out")
    undesired_languages: List[str] = Field(default_factory=list, description="Language codes to reject")
    max_posts_per_term: int = Field(default=40, ge=1, description="Post limit per term/country pair")
    max_pages: int = Field(default=5, ge=1, description="Max pages of search results to traverse")
    max_posts_total: int = Field(default=500, ge=1, description="Hard cap of leads to extract per run")

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> "SearchPreset":
        """Load and validate preset from a YAML file."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Preset file not found: {file_path}")
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            
        if not isinstance(data, dict):
            raise ValueError(f"Invalid YAML content in {file_path}; expected mapping")
            
        return cls(**data)


class Lead(BaseModel):
    """Represents an extracted and validated B2B lead from LinkedIn."""
    hash_id: str = Field(default="", description="Deterministic SHA-256 idempotency key")
    author_name: str = Field(default="N/A", description="Full name of lead")
    author_title: str = Field(default="N/A", description="Job title / headline")
    author_url: str = Field(default="N/A", description="LinkedIn profile URL")
    post_url: str = Field(default="N/A", description="URL to the specific post")
    post_text: str = Field(default="N/A", description="Extracted content text")
    post_date: str = Field(default="N/A", description="Relative or absolute post date")
    location: str = Field(default="N/A", description="Resolved or indicated location")
    search_term: str = Field(default="", description="Term that discovered this lead")
    country: str = Field(default="", description="Target country assigned")
    scraped_date: str = Field(default="", description="ISO timestamp of extraction")

    @model_validator(mode="after")
    def compute_deterministic_hash(self) -> "Lead":
        """Generate deterministic SHA-256 idempotency hash if not already provided."""
        if not self.hash_id:
            # When author_url and post_url exist and are not default placeholders
            author_val = self.author_url.strip() if self.author_url else "N/A"
            post_val = self.post_url.strip() if self.post_url else "N/A"

            if author_val != "N/A" or post_val != "N/A":
                raw_token = f"{author_val}{post_val}"
            else:
                raw_token = f"{self.author_name}:{self.post_text[:120]}:{self.post_date}"

            self.hash_id = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        if not self.scraped_date:
            self.scraped_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return self


class ExecutionStats(BaseModel):
    """Execution telemetry and tracking counters."""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    total_duration: float = 0.0
    posts_found: int = 0
    posts_added: int = 0
    posts_filtered: int = 0
    excluded_posts_filtered: int = 0
    errors_count: int = 0
    countries_processed: Dict[str, int] = Field(default_factory=dict)
    terms_processed: Dict[str, int] = Field(default_factory=dict)

    def record_country(self, country: str, count: int = 1) -> None:
        """Increment count for country."""
        self.countries_processed[country] = self.countries_processed.get(country, 0) + count

    def record_term(self, term: str, count: int = 1) -> None:
        """Increment count for search term."""
        self.terms_processed[term] = self.terms_processed.get(term, 0) + count
