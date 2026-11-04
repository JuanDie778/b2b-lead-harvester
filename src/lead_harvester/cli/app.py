"""Modern Command-Line Interface using Typer and Rich."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import time
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import typer

# Ensure Windows terminal standard streams handle UTF-8 properly
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from config.settings import get_settings
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from config.settings import get_settings

from ..core.logger import setup_logger
from ..core.models import ExecutionStats, SearchPreset
from ..engine.auth import LinkedInAuth
from ..engine.browser import BrowserSession
from ..engine.scraper import LeadScraper
from ..nlp.geo_validator import GeoValidator
from ..nlp.lang_filter import LanguageFilter
from ..storage.database import Database
from ..storage.exporters import LeadExporter

app = typer.Typer(
    name="harvest",
    help="Enterprise B2B Lead Harvester for LinkedIn.",
    add_completion=False,
)
console = Console()


@app.command(name="run")
def run_command(
    preset: Path = typer.Option(
        Path("config/presets/bim_aec.yaml"),
        "--preset",
        "-p",
        help="Path to YAML sector configuration preset.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of leads to extract in this run.",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run browser in headless or visible mode.",
    ),
    db: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Path to SQLite database file.",
    ),
    email: Optional[str] = typer.Option(
        None,
        "--email",
        "-e",
        help="LinkedIn email address (overrides .env).",
    ),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="LinkedIn password (overrides .env).",
    ),
    verify_profiles: bool = typer.Option(
        True,
        "--verify-profiles/--no-verify-profiles",
        help="Deep verify author locations by opening profile pages.",
    ),
) -> None:
    """Run the lead harvesting automation engine against LinkedIn."""
    settings = get_settings()
    setup_logger(level=settings.LOG_LEVEL)

    # 1. Load preset
    try:
        search_preset = SearchPreset.load_from_yaml(preset)
    except Exception as e:
        console.print(f"[bold red]Failed to load preset '{preset}':[/bold red] {e}")
        raise typer.Exit(code=1)

    # 2. Database
    db_path = db or settings.database_path
    database = Database(db_path)

    # 3. Credentials resolution
    target_email = email or settings.LINKEDIN_EMAIL
    target_password = password or settings.LINKEDIN_PASSWORD

    if not target_email or not target_password:
        console.print(
            Panel.fit(
                "[bold yellow]LinkedIn credentials required![/bold yellow]\n"
                "Please configure [green]LINKEDIN_EMAIL[/green] and [green]LINKEDIN_PASSWORD[/green] in your [cyan].env[/cyan] file,\n"
                "or pass them via [cyan]--email[/cyan] and [cyan]--password[/cyan].",
                title="Missing Credentials",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=1)

    console.print(
        Panel(
            f"[bold cyan]Preset:[/bold cyan] {search_preset.name}\n"
            f"[bold cyan]Database:[/bold cyan] {db_path}\n"
            f"[bold cyan]Headless Mode:[/bold cyan] {headless}\n"
            f"[bold cyan]Target Limit:[/bold cyan] {limit or search_preset.max_posts_total} leads\n"
            f"[bold cyan]Countries:[/bold cyan] {', '.join(search_preset.countries.keys())}",
            title="B2B Lead Harvester - Execution Plan",
            border_style="bright_blue",
        )
    )

    # 4. Async execution loop
    async def _async_run() -> ExecutionStats:
        stats = ExecutionStats(start_time=time.time())
        geo_val = GeoValidator(search_preset.excluded_indicators)
        lang_flt = LanguageFilter(search_preset.undesired_languages)

        scraper = LeadScraper(
            preset=search_preset,
            database=database,
            geo_validator=geo_val,
            lang_filter=lang_flt,
            stats=stats,
            verify_profile_locations=verify_profiles,
        )

        async with BrowserSession(headless=headless, timeout_ms=settings.BROWSER_TIMEOUT_MS) as session:
            await LinkedInAuth.login(
                page=session.page,
                email=target_email,
                password=target_password,
            )
            await scraper.harvest(
                page=session.page,
                context=session.context,
                target_limit=limit,
            )

        stats.end_time = time.time()
        stats.total_duration = stats.end_time - stats.start_time
        return stats

    try:
        stats = asyncio.run(_async_run())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Harvester execution interrupted by user.[/bold yellow]")
        raise typer.Exit(code=0)
    except Exception as e:
        console.print(f"[bold red]Harvester execution failed:[/bold red] {e}")
        raise typer.Exit(code=1)

    # 5. Display run metrics
    table = Table(title="Run Completion Summary", border_style="green")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="bold white")

    table.add_row("Total Duration", f"{stats.total_duration:.1f} s")
    table.add_row("Posts Discovered", str(stats.posts_found))
    table.add_row("Leads Added (New)", f"[green]{stats.posts_added}[/green]")
    table.add_row("Leads Filtered", str(stats.posts_filtered))
    table.add_row("Excluded Regions Blocked", str(stats.excluded_posts_filtered))
    table.add_row("Errors Encountered", str(stats.errors_count))
    table.add_row("Total DB Records", str(database.get_total_count()))

    console.print(table)


@app.command(name="export")
def export_command(
    format: str = typer.Option(
        "excel",
        "--format",
        "-f",
        help="Export format: 'excel' (.xlsx), 'csv', or 'json'.",
    ),
    output: Path = typer.Option(
        Path("./exports/leads.xlsx"),
        "--output",
        "-o",
        help="Target output file path.",
    ),
    country: Optional[str] = typer.Option(
        None,
        "--country",
        "-c",
        help="Filter leads by country.",
    ),
    term: Optional[str] = typer.Option(
        None,
        "--term",
        "-t",
        help="Filter leads by search term.",
    ),
    db: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Path to SQLite database file.",
    ),
) -> None:
    """Export collected leads from the SQLite database to CSV, Excel, or JSON."""
    settings = get_settings()
    db_path = db or settings.database_path

    if not db_path.exists():
        console.print(f"[bold red]Database file not found at:[/bold red] {db_path}")
        raise typer.Exit(code=1)

    database = Database(db_path)
    leads = database.get_leads(country=country, search_term=term)

    if not leads:
        console.print("[yellow]No leads found matching the specified filters.[/yellow]")
        raise typer.Exit(code=0)

    try:
        final_path = LeadExporter.export(leads, output_path=output, export_format=format)
        console.print(
            Panel.fit(
                f"[bold green]Successfully exported {len(leads)} leads![/bold green]\n"
                f"[cyan]Format:[/cyan] {format.upper()}\n"
                f"[cyan]Output File:[/cyan] {final_path.resolve()}",
                title="Export Completed",
                border_style="green",
            )
        )
    except Exception as e:
        console.print(f"[bold red]Export failed:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command(name="stats")
def stats_command(
    db: Optional[Path] = typer.Option(
        None,
        "--db",
        help="Path to SQLite database file.",
    ),
) -> None:
    """Display statistical overview of leads currently stored in the database."""
    settings = get_settings()
    db_path = db or settings.database_path

    if not db_path.exists():
        console.print(f"[yellow]Database not found at {db_path}. No leads collected yet.[/yellow]")
        raise typer.Exit(code=0)

    database = Database(db_path)
    stats = database.get_stats()
    total_leads = stats["total_leads"]

    console.print(
        Panel.fit(
            f"[bold green]Total Leads in Database:[/bold green] [bold white]{total_leads}[/bold white]\n"
            f"[dim]Database path: {db_path.resolve()}[/dim]",
            title="Lead Harvester Telemetry",
            border_style="cyan",
        )
    )

    if total_leads == 0:
        return

    # Leads by country
    c_table = Table(title="Leads by Country", border_style="magenta")
    c_table.add_column("Country", style="cyan")
    c_table.add_column("Count", style="green", justify="right")
    c_table.add_column("Percentage", style="yellow", justify="right")

    for country, count in stats["leads_by_country"].items():
        pct = (count / total_leads) * 100 if total_leads else 0
        c_table.add_row(country, str(count), f"{pct:.1f}%")

    console.print(c_table)

    # Leads by search term
    t_table = Table(title="Leads by Search Term", border_style="blue")
    t_table.add_column("Search Term", style="cyan")
    t_table.add_column("Count", style="green", justify="right")
    t_table.add_column("Percentage", style="yellow", justify="right")

    for term, count in stats["leads_by_term"].items():
        pct = (count / total_leads) * 100 if total_leads else 0
        t_table.add_row(term, str(count), f"{pct:.1f}%")

    console.print(t_table)


if __name__ == "__main__":
    app()
