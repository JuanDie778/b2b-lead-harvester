"""Logging infrastructure using Rich console output."""
import logging
from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logger(name: str = "lead_harvester", level: str = "INFO") -> logging.Logger:
    """Configure and return an enriched Rich logger."""
    logger = logging.getLogger(name)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Avoid adding duplicate handlers on multiple invocations
    if not logger.handlers:
        handler = RichHandler(
            console=console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            markup=True
        )
        formatter = logging.Formatter("%(message)s", datefmt="[%X]")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_logger(name: str = "lead_harvester") -> logging.Logger:
    """Retrieve logger instance."""
    return logging.getLogger(name)
