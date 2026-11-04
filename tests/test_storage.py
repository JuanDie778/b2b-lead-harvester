"""Unit tests for SQLite database persistence and multi-format exporters."""
import csv
import json
from pathlib import Path
import pandas as pd
import pytest
from lead_harvester.core.models import Lead
from lead_harvester.storage.database import Database
from lead_harvester.storage.exporters import LeadExporter


class TestDatabaseStorage:
    """Test suite for SQLite persistence, idempotency, and indexing."""

    def test_insert_single_lead(self, temp_db: Database, sample_lead: Lead):
        inserted = temp_db.insert_lead(sample_lead)
        assert inserted is True
        assert temp_db.get_total_count() == 1

    def test_idempotent_duplicate_ignored(self, temp_db: Database, sample_lead: Lead):
        # First insertion should succeed
        assert temp_db.insert_lead(sample_lead) is True

        # Exact duplicate insertion must be ignored (idempotent)
        assert temp_db.insert_lead(sample_lead) is False
        assert temp_db.get_total_count() == 1

    def test_deterministic_hash_uniqueness(self):
        lead1 = Lead(
            author_url="https://linkedin.com/in/unique-profile",
            post_url="https://linkedin.com/feed/update/123",
            author_name="Alice",
        )
        lead2 = Lead(
            author_url="https://linkedin.com/in/unique-profile",
            post_url="https://linkedin.com/feed/update/123",
            author_name="Alice Different Headline",
        )
        # Because author_url + post_url are identical, hash_id must be equal
        assert lead1.hash_id == lead2.hash_id
        assert len(lead1.hash_id) == 64  # SHA-256 hex string

    def test_insert_many(self, temp_db: Database, sample_lead: Lead):
        lead_clone = sample_lead.model_copy()
        lead_new = Lead(
            author_name="Bob Builder",
            author_url="https://linkedin.com/in/bob-builder",
            post_url="https://linkedin.com/feed/update/456",
            search_term="BIM Coordinator",
            country="Canada",
        )

        inserted, ignored = temp_db.insert_many([sample_lead, lead_clone, lead_new])
        assert inserted == 2
        assert ignored == 1
        assert temp_db.get_total_count() == 2

    def test_get_leads_filtering_and_pagination(self, temp_db: Database, sample_lead: Lead):
        temp_db.insert_lead(sample_lead)
        lead2 = Lead(
            author_name="Clara Oswald",
            author_url="https://linkedin.com/in/clara-oswald",
            post_url="https://linkedin.com/feed/update/789",
            search_term="Revit Modeler",
            country="Spain",
        )
        temp_db.insert_lead(lead2)

        # Filter by country
        uk_leads = temp_db.get_leads(country="United Kingdom")
        assert len(uk_leads) == 1
        assert uk_leads[0].author_name == "John Doe"

        spain_leads = temp_db.get_leads(country="Spain")
        assert len(spain_leads) == 1
        assert spain_leads[0].author_name == "Clara Oswald"

        # Filter with non-matching term
        empty_leads = temp_db.get_leads(search_term="Nonexistent Term")
        assert len(empty_leads) == 0

        # Pagination limit
        paged = temp_db.get_leads(limit=1)
        assert len(paged) == 1

        # Pagination offset without limit (must not raise SQLite syntax error)
        offset_leads = temp_db.get_leads(offset=1)
        assert len(offset_leads) == 1

        # Case-insensitive filtering
        ci_leads = temp_db.get_leads(country="united kingdom")
        assert len(ci_leads) == 1

    def test_hash_collision_prevention_missing_post_url(self, temp_db: Database):
        # Two distinct posts by the same author where post_url could not be resolved
        lead1 = Lead(
            author_url="https://linkedin.com/in/architect-jane",
            post_url="N/A",
            author_name="Jane",
            post_text="First post about BIM modeling in 2026",
            post_date="1d",
        )
        lead2 = Lead(
            author_url="https://linkedin.com/in/architect-jane",
            post_url="N/A",
            author_name="Jane",
            post_text="Second post about Revit automation workflows",
            post_date="2d",
        )
        assert lead1.hash_id != lead2.hash_id
        assert temp_db.insert_lead(lead1) is True
        assert temp_db.insert_lead(lead2) is True
        assert temp_db.get_total_count() == 2

    def test_get_stats(self, temp_db: Database, sample_lead: Lead):
        temp_db.insert_lead(sample_lead)
        stats = temp_db.get_stats()
        assert stats["total_leads"] == 1
        assert stats["leads_by_country"]["United Kingdom"] == 1
        assert stats["leads_by_term"]["BIM Manager"] == 1


class TestExporters:
    """Test suite for CSV, Excel, and JSON export pipelines."""

    @pytest.fixture
    def test_leads(self, sample_lead: Lead) -> list[Lead]:
        lead2 = Lead(
            author_name="Diana Prince",
            author_title="VDC Director",
            author_url="https://linkedin.com/in/diana-vdc",
            post_url="https://linkedin.com/feed/update/555",
            country="United States",
            search_term="VDC Engineer",
        )
        return [sample_lead, lead2]

    def test_export_to_csv(self, tmp_path: Path, test_leads: list[Lead]):
        csv_path = tmp_path / "leads.csv"
        out = LeadExporter.export_to_csv(test_leads, csv_path)
        assert out.exists()

        with open(out, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["author_name"] == "John Doe"
        assert rows[1]["country"] == "United States"

    def test_export_to_excel(self, tmp_path: Path, test_leads: list[Lead]):
        excel_path = tmp_path / "leads.xlsx"
        out = LeadExporter.export_to_excel(test_leads, excel_path)
        assert out.exists()

        df = pd.read_excel(out, engine="openpyxl")
        assert len(df) == 2
        assert "hash_id" in df.columns
        assert df.iloc[0]["author_name"] == "John Doe"

    def test_export_to_json(self, tmp_path: Path, test_leads: list[Lead]):
        json_path = tmp_path / "leads.json"
        out = LeadExporter.export_to_json(test_leads, json_path)
        assert out.exists()

        with open(out, mode="r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 2
        assert data[0]["author_name"] == "John Doe"
        assert data[1]["search_term"] == "VDC Engineer"

    def test_export_dispatcher_invalid_format(self, tmp_path: Path, test_leads: list[Lead]):
        with pytest.raises(ValueError, match="Unsupported export format"):
            LeadExporter.export(test_leads, tmp_path / "leads.pdf", export_format="pdf")

    def test_export_empty_list(self, tmp_path: Path):
        csv_path = tmp_path / "empty.csv"
        out = LeadExporter.export_to_csv([], csv_path)
        assert out.exists()
        with open(out, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert "hash_id" in header
