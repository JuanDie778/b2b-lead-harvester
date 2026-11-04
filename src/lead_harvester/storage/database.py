"""SQLite database persistence with deterministic SHA-256 deduplication."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, List, Optional, Tuple
from ..core.models import Lead


class Database:
    """Thread-safe SQLite database manager for B2B Leads."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS leads (
        hash_id TEXT PRIMARY KEY,
        author_name TEXT NOT NULL,
        author_title TEXT,
        author_url TEXT,
        post_url TEXT,
        post_text TEXT,
        post_date TEXT,
        location TEXT,
        search_term TEXT,
        country TEXT,
        scraped_date TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_leads_country ON leads(country);
    CREATE INDEX IF NOT EXISTS idx_leads_search_term ON leads(search_term);
    CREATE INDEX IF NOT EXISTS idx_leads_scraped_date ON leads(scraped_date);
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Create, configure, manage transaction and cleanly close SQLite connection."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            # Enable write-ahead logging for robustness and concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            with conn:
                yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize database tables and indexes."""
        with self._connection() as conn:
            conn.executescript(self.SCHEMA)

    def insert_lead(self, lead: Lead) -> bool:
        """
        Insert lead with INSERT OR IGNORE using deterministic hash_id.
        Returns True if inserted, False if duplicate ignored.
        """
        query = """
        INSERT OR IGNORE INTO leads (
            hash_id, author_name, author_title, author_url,
            post_url, post_text, post_date, location,
            search_term, country, scraped_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self._connection() as conn:
            cursor = conn.execute(
                query,
                (
                    lead.hash_id,
                    lead.author_name,
                    lead.author_title,
                    lead.author_url,
                    lead.post_url,
                    lead.post_text,
                    lead.post_date,
                    lead.location,
                    lead.search_term,
                    lead.country,
                    lead.scraped_date,
                ),
            )
            return cursor.rowcount > 0

    def insert_many(self, leads: List[Lead]) -> Tuple[int, int]:
        """
        Bulk insert leads.
        Returns tuple of (inserted_count, ignored_count).
        """
        if not leads:
            return 0, 0

        inserted = 0
        ignored = 0
        with self._connection() as conn:
            for lead in leads:
                query = """
                INSERT OR IGNORE INTO leads (
                    hash_id, author_name, author_title, author_url,
                    post_url, post_text, post_date, location,
                    search_term, country, scraped_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """
                cursor = conn.execute(
                    query,
                    (
                        lead.hash_id,
                        lead.author_name,
                        lead.author_title,
                        lead.author_url,
                        lead.post_url,
                        lead.post_text,
                        lead.post_date,
                        lead.location,
                        lead.search_term,
                        lead.country,
                        lead.scraped_date,
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    ignored += 1

        return inserted, ignored

    def get_leads(
        self,
        country: Optional[str] = None,
        search_term: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Lead]:
        """Retrieve stored leads with optional filtering and pagination."""
        clauses = []
        params: List[Any] = []

        if country:
            clauses.append("LOWER(country) = LOWER(?)")
            params.append(country)
        if search_term:
            clauses.append("LOWER(search_term) = LOWER(?)")
            params.append(search_term)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        if limit is not None:
            limit_sql = f"LIMIT {int(limit)}"
        elif offset > 0:
            # SQLite requires LIMIT when OFFSET is provided
            limit_sql = "LIMIT -1"
        else:
            limit_sql = ""

        offset_sql = f"OFFSET {int(offset)}" if offset > 0 else ""

        query = f"""
        SELECT hash_id, author_name, author_title, author_url,
               post_url, post_text, post_date, location,
               search_term, country, scraped_date
        FROM leads
        {where_sql}
        ORDER BY created_at DESC
        {limit_sql} {offset_sql};
        """

        with self._connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        return [
            Lead(
                hash_id=row["hash_id"],
                author_name=row["author_name"],
                author_title=row["author_title"],
                author_url=row["author_url"],
                post_url=row["post_url"],
                post_text=row["post_text"],
                post_date=row["post_date"],
                location=row["location"],
                search_term=row["search_term"],
                country=row["country"],
                scraped_date=row["scraped_date"],
            )
            for row in rows
        ]

    def get_total_count(self) -> int:
        """Return total number of unique leads in the database."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM leads;")
            return int(cursor.fetchone()[0])

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate statistical summary of collected leads."""
        with self._connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads;").fetchone()[0]

            countries = dict(
                conn.execute(
                    "SELECT country, COUNT(*) FROM leads GROUP BY country ORDER BY COUNT(*) DESC;"
                ).fetchall()
            )

            terms = dict(
                conn.execute(
                    "SELECT search_term, COUNT(*) FROM leads GROUP BY search_term ORDER BY COUNT(*) DESC;"
                ).fetchall()
            )

        return {
            "total_leads": total,
            "leads_by_country": countries,
            "leads_by_term": terms,
        }
