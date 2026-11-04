"""Application configuration using Pydantic Settings."""
from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings loaded from environment variables and .env file."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # LinkedIn Credentials
    LINKEDIN_EMAIL: str = Field(
        default="",
        description="LinkedIn account email for authentication."
    )
    LINKEDIN_PASSWORD: str = Field(
        default="",
        description="LinkedIn account password for authentication."
    )

    # Scraper Engine Settings
    HEADLESS_MODE: bool = Field(
        default=True,
        description="Run browser in headless mode."
    )
    BROWSER_TIMEOUT_MS: int = Field(
        default=30000,
        description="Playwright navigation timeout in milliseconds."
    )
    REQUEST_DELAY_MIN: float = Field(
        default=2.0,
        description="Minimum random delay between actions in seconds."
    )
    REQUEST_DELAY_MAX: float = Field(
        default=5.0,
        description="Maximum random delay between actions in seconds."
    )

    # Storage Settings
    DATA_DIR: Path = Field(
        default=Path("./data"),
        description="Directory for persistent data storage."
    )
    DATABASE_NAME: str = Field(
        default="leads.db",
        description="SQLite database file name."
    )
    
    # Logging
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)."
    )

    @property
    def database_path(self) -> Path:
        """Get absolute path to SQLite database, ensuring directory exists."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return self.DATA_DIR / self.DATABASE_NAME


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings singleton instance."""
    return Settings()
