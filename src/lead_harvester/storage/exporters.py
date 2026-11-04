"""Export engine for B2B leads supporting CSV, Excel (.xlsx), and JSON."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from ..core.models import Lead


class LeadExporter:
    """Handles multi-format data exports for collected leads."""

    EXPORT_COLUMNS = [
        "hash_id",
        "search_term",
        "country",
        "location",
        "author_name",
        "author_title",
        "author_url",
        "post_url",
        "post_text",
        "post_date",
        "scraped_date",
    ]

    @classmethod
    def _to_records(cls, leads: List[Lead]) -> List[Dict[str, Any]]:
        """Convert list of Lead models to dictionaries with uniform column order."""
        records = []
        for lead in leads:
            data = lead.model_dump()
            records.append({col: data.get(col, "N/A") for col in cls.EXPORT_COLUMNS})
        return records

    @classmethod
    def export_to_csv(cls, leads: List[Lead], output_path: str | Path) -> Path:
        """Export leads to a CSV file with UTF-8 BOM encoding for Excel compatibility."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        records = cls._to_records(leads)
        with open(path, mode="w", newline="", encoding="utf-8-sig") as f:
            if not records:
                writer = csv.DictWriter(f, fieldnames=cls.EXPORT_COLUMNS)
                writer.writeheader()
            else:
                writer = csv.DictWriter(f, fieldnames=cls.EXPORT_COLUMNS)
                writer.writeheader()
                writer.writerows(records)

        return path

    @classmethod
    def export_to_excel(cls, leads: List[Lead], output_path: str | Path) -> Path:
        """Export leads to an Excel (.xlsx) spreadsheet using pandas and openpyxl."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        records = cls._to_records(leads)
        df = pd.DataFrame(records, columns=cls.EXPORT_COLUMNS)
        df.to_excel(path, index=False, engine="openpyxl")
        return path

    @classmethod
    def export_to_json(cls, leads: List[Lead], output_path: str | Path) -> Path:
        """Export leads to a formatted JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        records = cls._to_records(leads)
        with open(path, mode="w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        return path

    @classmethod
    def export(cls, leads: List[Lead], output_path: str | Path, export_format: str) -> Path:
        """Dynamic exporter dispatcher based on format string."""
        fmt = export_format.lower().strip()
        path = Path(output_path)

        if fmt in ("excel", "xlsx"):
            if path.suffix.lower() != ".xlsx":
                path = path.with_suffix(".xlsx")
            return cls.export_to_excel(leads, path)
        elif fmt == "csv":
            if path.suffix.lower() != ".csv":
                path = path.with_suffix(".csv")
            return cls.export_to_csv(leads, path)
        elif fmt == "json":
            if path.suffix.lower() != ".json":
                path = path.with_suffix(".json")
            return cls.export_to_json(leads, path)
        else:
            raise ValueError(f"Unsupported export format '{export_format}'. Use 'csv', 'excel', or 'json'.")
