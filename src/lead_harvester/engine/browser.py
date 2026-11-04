"""Playwright browser lifecycle and session manager."""
from __future__ import annotations

import asyncio
from typing import Optional
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from ..core.logger import get_logger

logger = get_logger()

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class BrowserSession:
    """Async context manager handling Playwright browser, context, and page lifecycle."""

    def __init__(
        self,
        headless: bool = True,
        user_agent: Optional[str] = None,
        viewport_width: int = 1366,
        viewport_height: int = 768,
        timeout_ms: int = 30000,
    ):
        self.headless = headless
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.timeout_ms = timeout_ms

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def __aenter__(self) -> "BrowserSession":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Start Playwright runtime and launch browser."""
        logger.info(f"[cyan]Initializing Playwright engine (Headless: {self.headless})...[/cyan]")
        self.playwright = await async_playwright().start()

        args = ["--start-maximized", "--disable-blink-features=AutomationControlled"]
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=args,
        )

        self.context = await self.browser.new_context(
            user_agent=self.user_agent,
            viewport=self.viewport,
            locale="en-US",
            timezone_id="America/New_York",
        )
        self.context.set_default_timeout(self.timeout_ms)

        self.page = await self.context.new_page()
        logger.info("[green]Browser session initialized successfully.[/green]")

    async def close(self) -> None:
        """Gracefully terminate page, context, browser, and playwright engine."""
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass

        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass

        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass

        logger.info("[dim]Browser session closed.[/dim]")
