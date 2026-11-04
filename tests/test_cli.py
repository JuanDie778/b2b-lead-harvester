"""Integration tests for Typer CLI commands."""
from pathlib import Path
import pytest
from typer.testing import CliRunner
from lead_harvester.cli.app import app
from lead_harvester.core.models import Lead
from lead_harvester.storage.database import Database

runner = CliRunner()


class TestCliCommands:
    """Test suite for CLI invocation, arguments, and outputs."""

    def test_cli_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Enterprise B2B Lead Harvester" in result.stdout
        assert "run" in result.stdout
        assert "export" in result.stdout
        assert "stats" in result.stdout

    def test_stats_command_nonexistent_db(self, tmp_path: Path):
        fake_db = tmp_path / "not_there.db"
        result = runner.invoke(app, ["stats", "--db", str(fake_db)])
        assert result.exit_code == 0
        assert "Database not found" in result.stdout or "No leads collected yet" in result.stdout

    def test_stats_command_populated_db(self, temp_db: Database, sample_lead: Lead):
        temp_db.insert_lead(sample_lead)
        result = runner.invoke(app, ["stats", "--db", str(temp_db.db_path)])
        assert result.exit_code == 0
        assert "Total Leads in Database: 1" in result.stdout
        assert "United Kingdom" in result.stdout
        assert "BIM Manager" in result.stdout

    def test_export_command_csv(self, temp_db: Database, sample_lead: Lead, tmp_path: Path):
        temp_db.insert_lead(sample_lead)
        out_file = tmp_path / "exported_leads.csv"
        result = runner.invoke(
            app,
            ["export", "--db", str(temp_db.db_path), "--format", "csv", "--output", str(out_file)],
        )
        assert result.exit_code == 0
        assert out_file.exists()
        assert "Successfully exported 1 leads" in result.stdout

    def test_export_command_excel(self, temp_db: Database, sample_lead: Lead, tmp_path: Path):
        temp_db.insert_lead(sample_lead)
        out_file = tmp_path / "exported_leads.xlsx"
        result = runner.invoke(
            app,
            ["export", "--db", str(temp_db.db_path), "--format", "excel", "--output", str(out_file)],
        )
        assert result.exit_code == 0
        assert out_file.exists()
        assert "Successfully exported 1 leads" in result.stdout

    def test_export_command_json(self, temp_db: Database, sample_lead: Lead, tmp_path: Path):
        temp_db.insert_lead(sample_lead)
        out_file = tmp_path / "exported_leads.json"
        result = runner.invoke(
            app,
            ["export", "--db", str(temp_db.db_path), "--format", "json", "--output", str(out_file)],
        )
        assert result.exit_code == 0
        assert out_file.exists()
        assert "Successfully exported 1 leads" in result.stdout

    def test_export_command_no_matches(self, temp_db: Database, sample_lead: Lead, tmp_path: Path):
        temp_db.insert_lead(sample_lead)
        out_file = tmp_path / "filtered_out.csv"
        result = runner.invoke(
            app,
            ["export", "--db", str(temp_db.db_path), "--country", "NonexistentCountry", "--output", str(out_file)],
        )
        assert result.exit_code == 0
        assert "No leads found matching" in result.stdout

    def test_run_command_missing_credentials_fails_cleanly(self, tmp_path: Path, sample_preset_yaml: Path):
        db_file = tmp_path / "harvest_test.db"
        result = runner.invoke(
            app,
            [
                "run",
                "--preset",
                str(sample_preset_yaml),
                "--db",
                str(db_file),
                "--email",
                "",
                "--password",
                "",
            ],
        )
        assert result.exit_code == 1
        assert "LinkedIn credentials required" in result.stdout
