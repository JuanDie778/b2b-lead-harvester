"""Domain-agnostic asynchronous LinkedIn lead scraping engine."""
from __future__ import annotations

import asyncio
from datetime import datetime
import random
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from playwright.async_api import BrowserContext, ElementHandle, Page
from ..core.logger import get_logger
from ..core.models import CountryTarget, ExecutionStats, Lead, SearchPreset
from ..nlp.geo_validator import GeoValidator
from ..nlp.lang_filter import LanguageFilter
from ..storage.database import Database
from .auth import LinkedInAuth

logger = get_logger()


class LeadScraper:
    """Asynchronous extraction engine for LinkedIn B2B posts and profiles."""

    def __init__(
        self,
        preset: SearchPreset,
        database: Database,
        geo_validator: Optional[GeoValidator] = None,
        lang_filter: Optional[LanguageFilter] = None,
        stats: Optional[ExecutionStats] = None,
        verify_profile_locations: bool = True,
    ):
        self.preset = preset
        self.db = database
        self.geo_validator = geo_validator or GeoValidator(preset.excluded_indicators)
        self.lang_filter = lang_filter or LanguageFilter(preset.undesired_languages)
        self.stats = stats or ExecutionStats()
        self.verify_profile_locations = verify_profile_locations

    @staticmethod
    def _extract_activity_id(data_urn: Optional[str]) -> Optional[str]:
        """Convert URN into canonical feed URL."""
        if data_urn and ("urn:li:activity:" in data_urn or "urn:li:ugcPost:" in data_urn):
            activity_id = data_urn.split(":")[-1]
            return f"https://www.linkedin.com/feed/update/{activity_id}/"
        return None

    async def extract_post_data(self, post: ElementHandle) -> Dict[str, str]:
        """Extract structured data fields from a single post DOM node."""
        # 1. Author Name
        author_name = "N/A"
        try:
            name_el = await post.query_selector(".update-components-actor__name")
            if name_el:
                author_name = (await name_el.inner_text()).strip()
        except Exception:
            pass

        # 2. Author Headline / Title
        author_title = "N/A"
        try:
            title_el = await post.query_selector(".update-components-actor__description")
            if title_el:
                author_title = (await title_el.inner_text()).strip()
        except Exception:
            pass

        # 3. Author Profile URL
        author_url = "N/A"
        try:
            profile_selectors = [
                'a.app-aware-link[href*="/in/"]',
                ".update-components-actor__container a",
                ".update-components-actor__name-link",
            ]
            for sel in profile_selectors:
                link_el = await post.query_selector(sel)
                if link_el:
                    href = await link_el.get_attribute("href")
                    if href:
                        author_url = href.split("?")[0].strip()
                        break
        except Exception:
            pass

        # 4. Post URL
        post_url = "N/A"
        try:
            # Check data-urn attribute directly on root post element first
            root_urn = await post.get_attribute("data-urn")
            if root_urn:
                extracted = self._extract_activity_id(root_urn)
                if extracted:
                    post_url = extracted
        except Exception:
            pass

        if post_url == "N/A":
            try:
                strategies = [
                    ('a.app-aware-link[href*="/feed/update/"]', "href"),
                    ('a[data-id*="share-"]', "href"),
                    ('[data-urn*="urn:li:activity:"]', "data-urn"),
                    ('[data-urn*="urn:li:ugcPost:"]', "data-urn"),
                    (".feed-shared-update-v2", "data-urn"),
                ]
                for sel, attr in strategies:
                    el = await post.query_selector(sel)
                    if el:
                        val = await el.get_attribute(attr)
                        if val:
                            if attr == "data-urn":
                                extracted = self._extract_activity_id(val)
                                if extracted:
                                    post_url = extracted
                                    break
                            elif "/feed/update/" in val:
                                post_url = val.split("?")[0].strip()
                                break
            except Exception:
                pass

        # 5. Post Text Content
        post_text = "N/A"
        try:
            text_el = await post.query_selector(".update-components-text")
            if text_el:
                raw_text = await text_el.inner_text()
                post_text = raw_text.strip()[:1000]
        except Exception:
            pass

        # 6. Post Date
        post_date = "N/A"
        try:
            date_el = await post.query_selector(".update-components-actor__sub-description")
            if date_el:
                raw_date = await date_el.inner_text()
                post_date = re.sub(r"•.*", "", raw_date).strip()
        except Exception:
            pass

        # 7. Location
        location = "N/A"
        try:
            loc_el = await post.query_selector(
                ".update-components-actor__sub-description .update-components-actor__distance"
            )
            if loc_el:
                location = (await loc_el.inner_text()).strip()
        except Exception:
            pass

        return {
            "author_name": author_name,
            "author_title": author_title,
            "author_url": author_url,
            "post_url": post_url,
            "post_text": post_text,
            "post_date": post_date,
            "location": location,
        }

    async def verify_author_profile_location(
        self,
        context: BrowserContext,
        author_url: str,
        country: str,
        country_target: CountryTarget,
    ) -> bool:
        """Inspect the author's public profile page to confirm their geographic location."""
        if not author_url or author_url == "N/A":
            return False

        profile_page = None
        try:
            profile_page = await context.new_page()
            await profile_page.goto(author_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1.5)

            loc_selectors = [
                ".text-body-small.inline.t-black--light.break-words",
                ".pv-top-card--list-bullet li",
                ".pv-top-card-v2--list-bullet li",
                ".top-card__subline-item",
            ]

            location_text = ""
            for sel in loc_selectors:
                el = await profile_page.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    if text:
                        location_text = text
                        break

            if location_text:
                if self.geo_validator.is_excluded(location_text):
                    return False
                return self.geo_validator.verify_location_string(
                    location=location_text,
                    country=country,
                    country_target=country_target,
                )
        except Exception as e:
            logger.debug(f"Profile location verification skipped for {author_url}: {e}")
            return False
        finally:
            if profile_page:
                try:
                    await profile_page.close()
                except Exception:
                    pass

        return False

    async def scroll_down(self, page: Page, times: int = 3) -> None:
        """Scroll smoothly to trigger progressive rendering of LinkedIn posts."""
        for _ in range(times):
            await page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
            await asyncio.sleep(random.uniform(1.5, 3.0))

    async def go_to_next_page(self, page: Page) -> bool:
        """Navigate to the next page of content search results."""
        next_selectors = [
            'button[aria-label="Next"]',
            'button[aria-label="Siguiente"]',
            ".artdeco-pagination__button--next",
        ]
        for sel in next_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    is_disabled = await btn.get_attribute("disabled")
                    if not is_disabled and await btn.is_visible():
                        await btn.click()
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(random.uniform(2.5, 4.0))
                        return True
            except Exception:
                continue
        return False

    async def harvest(
        self,
        page: Page,
        context: BrowserContext,
        target_limit: Optional[int] = None,
    ) -> ExecutionStats:
        """Execute full lead harvesting loop according to preset parameters."""
        limit = target_limit or self.preset.max_posts_total
        logger.info(
            f"[bold blue]Starting lead harvesting[/bold blue] (Target limit: {limit} leads, "
            f"Preset: '{self.preset.name}')"
        )

        for country_name, country_target in self.preset.countries.items():
            if self.stats.posts_added >= limit:
                logger.info("[bold green]Harvesting goal reached. Stopping.[/bold green]")
                break

            logger.info(f"\n[bold magenta]=== Region: {country_name} ===[/bold magenta]")

            for term_idx, search_term in enumerate(self.preset.search_terms):
                if self.stats.posts_added >= limit:
                    break

                term_leads_count = 0
                logger.info(
                    f"Searching for [bold yellow]'{search_term}'[/bold yellow] in {country_name} "
                    f"({term_idx + 1}/{len(self.preset.search_terms)})"
                )

                encoded_term = quote(search_term, safe="")
                search_url = (
                    f"https://www.linkedin.com/search/results/content/?"
                    f"keywords={encoded_term}"
                    f"&facetGeoRegion={country_target.code}"
                    f"&facetContentType=%22posts%22"
                )

                try:
                    await page.goto(search_url, wait_until="domcontentloaded")
                    await asyncio.sleep(random.uniform(2.5, 4.0))
                    await LinkedInAuth.dismiss_popups(page)
                except Exception as e:
                    logger.error(f"Navigation failed for '{search_term}': {e}")
                    self.stats.errors_count += 1
                    continue

                page_num = 0
                while page_num < self.preset.max_pages:
                    if self.stats.posts_added >= limit:
                        break
                    if term_leads_count >= self.preset.max_posts_per_term:
                        logger.info(f"Reached per-term limit ({self.preset.max_posts_per_term}) for '{search_term}'")
                        break

                    page_num += 1
                    logger.info(f"Scanning page {page_num}/{self.preset.max_pages}...")

                    try:
                        await page.wait_for_selector(".feed-shared-update-v2", timeout=8000)
                    except Exception:
                        logger.info("No posts loaded on this page.")
                        break

                    await self.scroll_down(page, times=2)
                    posts = await page.query_selector_all(".feed-shared-update-v2")
                    self.stats.posts_found += len(posts)

                    for post in posts:
                        if self.stats.posts_added >= limit or term_leads_count >= self.preset.max_posts_per_term:
                            break

                        try:
                            data = await self.extract_post_data(post)
                            post_text = data["post_text"]
                            author_title = data["author_title"]
                            combined_text = f"{author_title} {post_text} {data['location']}"

                            # 1. Exclusion filter
                            if self.geo_validator.is_excluded(combined_text):
                                self.stats.posts_filtered += 1
                                self.stats.excluded_posts_filtered += 1
                                continue

                            # 2. Language filter
                            if not self.lang_filter.is_accepted(post_text):
                                self.stats.posts_filtered += 1
                                continue

                            # 3. Geo location verification
                            verified = self.geo_validator.verify_content(
                                text=combined_text,
                                country=country_name,
                                country_target=country_target,
                            )

                            if not verified and self.verify_profile_locations and data["author_url"] != "N/A":
                                verified = await self.verify_author_profile_location(
                                    context=context,
                                    author_url=data["author_url"],
                                    country=country_name,
                                    country_target=country_target,
                                )

                            if not verified:
                                self.stats.posts_filtered += 1
                                continue

                            # Resolved location
                            resolved_loc = (
                                data["location"]
                                if data["location"] != "N/A"
                                else (random.choice(country_target.location_names) if country_target.location_names else country_name)
                            )

                            lead = Lead(
                                author_name=data["author_name"],
                                author_title=data["author_title"],
                                author_url=data["author_url"],
                                post_url=data["post_url"],
                                post_text=post_text,
                                post_date=data["post_date"],
                                location=resolved_loc,
                                search_term=search_term,
                                country=country_name,
                                scraped_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            )

                            inserted = self.db.insert_lead(lead)
                            if inserted:
                                self.stats.posts_added += 1
                                term_leads_count += 1
                                self.stats.record_country(country_name, 1)
                                self.stats.record_term(search_term, 1)
                                logger.info(
                                    f"  [green]+ Lead stored[/green]: {lead.author_name} ({lead.author_title[:40]}) "
                                    f"[{lead.country}]"
                                )
                            else:
                                logger.debug(f"Duplicate lead ignored: {lead.hash_id[:10]}")

                        except Exception as e:
                            self.stats.errors_count += 1
                            logger.debug(f"Error extracting post node: {e}")

                    # Attempt pagination
                    has_next = await self.go_to_next_page(page)
                    if not has_next:
                        break

                # Polite pause between search terms
                await asyncio.sleep(random.uniform(2.0, 4.0))

        return self.stats
