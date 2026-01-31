"""Wellfound (AngelList) job collector via web scraping."""
import asyncio
import re
from datetime import datetime
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseCollector, JobData


class WellfoundCollector(BaseCollector):
    """Collector for Wellfound (formerly AngelList Talent) jobs."""

    name = "wellfound"
    BASE_URL = "https://wellfound.com"

    def __init__(self, timeout: int = 30, pages: int = 3):
        """
        Initialize Wellfound collector.

        Args:
            timeout: Request timeout in seconds
            pages: Number of pages to fetch per search
        """
        self.timeout = timeout
        self.pages = pages

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from Wellfound."""
        all_jobs: list[JobData] = []

        async with aiohttp.ClientSession() as session:
            for query in search_queries:
                try:
                    jobs = await self._search(session, query)
                    all_jobs.extend(jobs)
                except Exception as e:
                    print(f"Wellfound error for query '{query}': {e}")

        return all_jobs

    async def _search(
        self,
        session: aiohttp.ClientSession,
        query: str,
    ) -> list[JobData]:
        """Search Wellfound for jobs."""
        jobs: list[JobData] = []

        # Format query for URL
        query_slug = query.lower().replace(" ", "-")

        for page in range(1, self.pages + 1):
            try:
                url = f"{self.BASE_URL}/role/{query_slug}"
                if page > 1:
                    url += f"?page={page}"

                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                ) as response:
                    if response.status != 200:
                        break

                    html = await response.text()
                    page_jobs = self._parse_page(html, query)
                    jobs.extend(page_jobs)

                    if not page_jobs:  # No more results
                        break

                # Be nice to the server
                await asyncio.sleep(1)

            except asyncio.TimeoutError:
                print(f"Wellfound timeout for page {page}")
                break
            except Exception as e:
                print(f"Wellfound page error: {e}")
                break

        return jobs

    def _parse_page(self, html: str, query: str) -> list[JobData]:
        """Parse a Wellfound search results page."""
        jobs: list[JobData] = []

        try:
            soup = BeautifulSoup(html, "html.parser")

            # Find job cards (structure may change)
            job_cards = soup.find_all("div", {"class": re.compile(r"job.*card", re.I)})

            if not job_cards:
                # Try alternative selectors
                job_cards = soup.find_all("a", href=re.compile(r"/jobs/"))

            for card in job_cards:
                job = self._parse_card(card, query)
                if job:
                    jobs.append(job)

        except Exception as e:
            print(f"Wellfound parse error: {e}")

        return jobs

    def _parse_card(self, card, query: str) -> Optional[JobData]:
        """Parse a job card element."""
        try:
            # Extract title
            title_elem = card.find(["h2", "h3", "h4"]) or card.find(
                class_=re.compile(r"title", re.I)
            )
            title = title_elem.get_text(strip=True) if title_elem else query.title()

            # Extract company
            company_elem = card.find(class_=re.compile(r"company", re.I))
            company = (
                company_elem.get_text(strip=True)
                if company_elem
                else "Unknown Company"
            )

            # Extract URL
            url = None
            if card.name == "a":
                url = card.get("href", "")
            else:
                link = card.find("a", href=re.compile(r"/jobs/"))
                url = link.get("href", "") if link else ""

            if url and not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            if not url:
                return None

            # Extract location
            location_elem = card.find(class_=re.compile(r"location", re.I))
            location = location_elem.get_text(strip=True) if location_elem else None

            # Check for remote
            is_remote = False
            if location:
                is_remote = any(
                    term in location.lower()
                    for term in ["remote", "anywhere", "worldwide"]
                )

            # Extract salary if available
            salary_min = None
            salary_max = None
            salary_elem = card.find(class_=re.compile(r"salary|compensation", re.I))
            if salary_elem:
                salary_text = salary_elem.get_text()
                salary_match = re.findall(r"\$[\d,]+k?", salary_text, re.I)
                if len(salary_match) >= 2:
                    try:
                        salary_min = int(
                            salary_match[0].replace("$", "").replace(",", "").replace("k", "000")
                        )
                        salary_max = int(
                            salary_match[1].replace("$", "").replace(",", "").replace("k", "000")
                        )
                    except ValueError:
                        pass

            return JobData(
                title=title,
                company=company,
                url=url,
                source="wellfound",
                location=location,
                description=None,
                salary_min=salary_min,
                salary_max=salary_max,
                apply_url=url,
                remote=is_remote,
                posted_date=datetime.now(),  # Wellfound doesn't show dates easily
            )

        except Exception as e:
            print(f"Wellfound card parse error: {e}")
            return None
