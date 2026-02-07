"""The Muse job board collector."""
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseCollector, JobData
from .utils import http_get_json

logger = logging.getLogger(__name__)


class TheMuseCollector(BaseCollector):
    """Collector for The Muse public jobs API."""

    name = "themuse"
    API_URL = "https://www.themuse.com/api/public/jobs"

    # Remote-indicating terms in location strings
    REMOTE_TERMS = {"remote", "flexible", "anywhere"}

    def __init__(
        self,
        timeout: int = 30,
        max_pages: int = 5,
        delay_between_pages: tuple[float, float] = (0.5, 1.5),
    ):
        """
        Initialize The Muse collector.

        Args:
            timeout: Request timeout in seconds.
            max_pages: Maximum pages to fetch per query (20 results/page).
            delay_between_pages: Min/max seconds delay between page fetches.
        """
        self.timeout = timeout
        self.max_pages = max_pages
        self.delay_range = delay_between_pages

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from The Muse API."""
        all_jobs: list[JobData] = []
        seen_urls: set[str] = set()

        async with aiohttp.ClientSession() as session:
            for query in search_queries:
                try:
                    jobs = await self._fetch_query(session, query)
                    for job in jobs:
                        if job.url and job.url not in seen_urls:
                            seen_urls.add(job.url)
                            all_jobs.append(job)
                except Exception as e:
                    logger.error("The Muse error for query '%s': %s", query, e)

                # Rate limiting between queries
                delay = random.uniform(*self.delay_range)
                await asyncio.sleep(delay)

        logger.info("The Muse collected %d unique jobs", len(all_jobs))
        return all_jobs

    async def _fetch_query(
        self,
        session: aiohttp.ClientSession,
        query: str,
    ) -> list[JobData]:
        """Fetch paginated results for a single search query."""
        jobs: list[JobData] = []

        for page in range(self.max_pages):
            params = {"page": page, "category": query}
            try:
                data = await http_get_json(
                    session,
                    self.API_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                )
                if data is None:
                    logger.debug(
                        "The Muse returned no data for query '%s' page %d",
                        query, page,
                    )
                    break

                results = data.get("results", [])
                if not results:
                    break

                for item in results:
                    job = self._parse_job(item)
                    if job:
                        jobs.append(job)

                # Stop if we've reached the last page
                page_count = data.get("page_count", 0)
                if page + 1 >= page_count:
                    break

                # Rate limiting between pages
                delay = random.uniform(*self.delay_range)
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(
                    "The Muse error fetching page %d for '%s': %s",
                    page, query, e,
                )
                break

        return jobs

    def _parse_job(self, data: dict) -> Optional[JobData]:
        """Parse a Muse job result into a JobData object."""
        try:
            # Title
            title = data.get("name", "")
            if not title:
                return None

            # Company
            company_data = data.get("company", {}) or {}
            company = company_data.get("name", "")

            # URL
            refs = data.get("refs", {}) or {}
            url = refs.get("landing_page", "")

            # Locations
            locations_list = data.get("locations", []) or []
            location_names = [
                loc.get("name", "") for loc in locations_list if loc.get("name")
            ]
            location = "; ".join(location_names) if location_names else None

            # Remote detection
            is_remote = False
            if location:
                location_lower = location.lower()
                is_remote = any(
                    term in location_lower for term in self.REMOTE_TERMS
                )

            # Description — strip HTML
            description = data.get("contents", "")
            if description:
                soup = BeautifulSoup(description, "html.parser")
                description = soup.get_text(separator=" ", strip=True)

            # Posted date
            posted_date = None
            pub_date = data.get("publication_date")
            if pub_date:
                try:
                    posted_date = datetime.fromisoformat(
                        pub_date.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Levels
            levels = data.get("levels", []) or []
            level_names = [
                lvl.get("name", "") for lvl in levels if lvl.get("name")
            ]

            # Categories
            categories = data.get("categories", []) or []
            category_names = [
                cat.get("name", "") for cat in categories if cat.get("name")
            ]

            return JobData(
                title=title,
                company=company,
                url=url,
                source="themuse",
                location=location,
                description=description,
                salary_min=None,
                salary_max=None,
                apply_url=url,
                remote=is_remote,
                posted_date=posted_date,
                extra_data={
                    "levels": level_names,
                    "categories": category_names,
                },
            )
        except Exception as e:
            logger.error("Error parsing The Muse job: %s", e)
            return None
