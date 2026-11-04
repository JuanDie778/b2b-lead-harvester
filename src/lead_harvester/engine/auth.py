"""Resilient authentication and session management for LinkedIn."""
from __future__ import annotations

import asyncio
import random
from typing import Optional
from playwright.async_api import Page
from ..core.logger import get_logger

logger = get_logger()


class LinkedInAuth:
    """Manages LinkedIn credentials login and popup dismissal."""

    POPUP_SELECTORS = [
        ".artdeco-modal__dismiss",
        ".msg-overlay-bubble-header__control",
        'button[aria-label="Dismiss"]',
        'button[aria-label="Cerrar"]',
        'button[aria-label="Got it"]',
        '.modal__dismiss',
    ]

    SEARCH_INPUT_SELECTORS = [
        'input[aria-label="Buscar"]',
        'input[aria-label="Search"]',
        '.search-global-typeahead__input',
        '#global-nav-typeahead input',
        'nav.global-nav',
    ]

    @classmethod
    async def is_authenticated(cls, page: Page, timeout: int = 5000) -> bool:
        """Check if session is already active by looking for the main search input."""
        for selector in cls.SEARCH_INPUT_SELECTORS:
            try:
                el = await page.wait_for_selector(selector, timeout=timeout)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue
        return False

    @classmethod
    async def dismiss_popups(cls, page: Page) -> None:
        """Dismiss common LinkedIn overlay modals and message popups."""
        try:
            for selector in cls.POPUP_SELECTORS:
                try:
                    buttons = await page.query_selector_all(selector)
                    for btn in buttons:
                        try:
                            if await btn.is_visible():
                                await btn.click()
                                await asyncio.sleep(0.3)
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Popup dismissal skipped or failed: {e}")

    @classmethod
    async def login(
        cls,
        page: Page,
        email: str,
        password: str,
        max_retries: int = 3,
        initial_delay: float = 2.0,
        backoff_factor: float = 2.0,
    ) -> bool:
        """
        Authenticate into LinkedIn with exponential backoff retry.
        Raises ValueError if credentials are missing or login fails after retries.
        """
        if not email or not password:
            raise ValueError(
                "LinkedIn credentials missing. Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env"
            )

        attempt = 0
        current_delay = initial_delay

        while attempt < max_retries:
            attempt += 1
            logger.info(f"[cyan]Authentication attempt {attempt}/{max_retries}...[/cyan]")

            try:
                await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(1.0, 2.5))

                if await cls.is_authenticated(page, timeout=3000):
                    logger.info("[bold green]Already authenticated in LinkedIn.[/bold green]")
                    return True

                # Fill username with slight jitter
                await page.wait_for_selector("#username", timeout=10000)
                await page.fill("#username", email)
                await asyncio.sleep(random.uniform(0.3, 0.8))

                # Fill password
                await page.fill("#password", password)
                await asyncio.sleep(random.uniform(0.3, 0.8))

                # Click submit
                await page.click('button[type="submit"]')

                # Check for successful landing
                if await cls.is_authenticated(page, timeout=15000):
                    logger.info("[bold green]Successfully authenticated into LinkedIn.[/bold green]")
                    await cls.dismiss_popups(page)
                    return True

                # Inspect for explicit error banner
                error_el = await page.query_selector(".alert-error, #error-for-password, #error-for-username")
                if error_el:
                    err_text = await error_el.inner_text()
                    logger.warning(f"[yellow]Login error returned: {err_text.strip()}[/yellow]")

            except Exception as e:
                logger.warning(f"[yellow]Login attempt {attempt} encountered error: {e}[/yellow]")

            if attempt < max_retries:
                logger.info(f"Retrying login in {current_delay:.1f}s...")
                await asyncio.sleep(current_delay)
                current_delay *= backoff_factor

        raise RuntimeError(f"Failed to authenticate into LinkedIn after {max_retries} attempts.")
