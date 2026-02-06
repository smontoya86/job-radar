"""Search Discovery collector — discovers new company job boards via SerpApi site: queries."""
import asyncio
import re
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData


class SearchDiscoveryCollector(BaseCollector):
    """
    Collector that uses SerpApi to discover new company job boards.

    Runs site: queries against known ATS domains (Greenhouse, Lever, Ashby)
    to find companies hiring for roles matching the search queries. Designed
    to run less frequently (daily) for board discovery rather than real-time
    job collection.
    """

    name = "search_discovery"
    BASE_URL = "https://serpapi.com/search"
    MAX_QUERIES_PER_RUN = 10
    DELAY_BETWEEN_REQUESTS = 2.0

    ATS_DOMAINS = [
        "boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.ashbyhq.com",
    ]

    # Patterns to extract company slug from ATS URLs
    _COMPANY_PATTERNS = {
        "boards.greenhouse.io": re.compile(
            r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)"
        ),
        "jobs.lever.co": re.compile(
            r"jobs\.lever\.co/([a-zA-Z0-9_-]+)"
        ),
        "jobs.ashbyhq.com": re.compile(
            r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)"
        ),
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Search Discovery collector.

        Args:
            api_key: SerpApi API key. If not provided, the collector will skip.
        """
        self.api_key = api_key

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """
        Discover job board URLs by running site: queries against ATS domains.

        Iterates over (query, domain) pairs up to MAX_QUERIES_PER_RUN total,
        with a DELAY_BETWEEN_REQUESTS second pause between each SerpApi call.

        Args:
            search_queries: List of search terms/job titles to search for.

        Returns:
            List of JobData objects representing discovered job board pages.
        """
        if not self.api_key:
            print("Search Discovery: no SerpApi key configured, skipping")
            return []

        all_jobs: list[JobData] = []
        queries_executed = 0

        async with aiohttp.ClientSession() as session:
            for query in search_queries:
                for domain in self.ATS_DOMAINS:
                    if queries_executed >= self.MAX_QUERIES_PER_RUN:
                        return all_jobs

                    try:
                        jobs = await self._search(session, query, domain)
                        all_jobs.extend(jobs)
                    except Exception as e:
                        print(
                            f"Search Discovery error for "
                            f"'{query}' on {domain}: {e}"
                        )

                    queries_executed += 1

                    # Rate-limit: wait between requests
                    if queries_executed < self.MAX_QUERIES_PER_RUN:
                        await asyncio.sleep(self.DELAY_BETWEEN_REQUESTS)

        return all_jobs

    async def _search(
        self,
        session: aiohttp.ClientSession,
        query: str,
        domain: str,
    ) -> list[JobData]:
        """
        Run a single SerpApi Google search for a site:-scoped query.

        Args:
            session: Active aiohttp session.
            query: The job search term (e.g. "product manager").
            domain: The ATS domain to scope to (e.g. "boards.greenhouse.io").

        Returns:
            List of JobData objects parsed from organic results.
        """
        params = {
            "engine": "google",
            "q": f'site:{domain} "{query}"',
            "api_key": self.api_key,
        }

        async with session.get(self.BASE_URL, params=params) as response:
            if response.status != 200:
                print(
                    f"Search Discovery: SerpApi returned status "
                    f"{response.status} for '{query}' on {domain}"
                )
                return []

            data = await response.json()
            jobs: list[JobData] = []

            for result in data.get("organic_results", []):
                job = self._parse_result(result, domain)
                if job:
                    jobs.append(job)

            return jobs

    def _parse_result(
        self, result: dict, domain: str
    ) -> Optional[JobData]:
        """
        Parse a single SerpApi organic result into a JobData object.

        Extracts the company name from the URL path segment for the given
        ATS domain.

        Args:
            result: A single organic_results entry from SerpApi.
            domain: The ATS domain used in the query.

        Returns:
            A JobData object, or None if parsing fails.
        """
        try:
            link = result.get("link", "")
            title = result.get("title", "")
            snippet = result.get("snippet", "")

            if not link:
                return None

            # Extract company slug from the URL
            company = self._extract_company(link, domain)

            return JobData(
                title=title,
                company=company,
                url=link,
                source="search_discovery",
                description=snippet,
                extra_data={
                    "ats_domain": domain,
                    "discovery_date": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            print(f"Search Discovery: error parsing result: {e}")
            return None

    def _extract_company(self, url: str, domain: str) -> str:
        """
        Extract company name from an ATS URL.

        Examples:
            boards.greenhouse.io/anthropic  -> "Anthropic"
            jobs.lever.co/netflix           -> "Netflix"
            jobs.ashbyhq.com/ramp           -> "Ramp"

        Args:
            url: The full URL from the search result.
            domain: The ATS domain to match against.

        Returns:
            Human-readable company name (title-cased), or "Unknown" if
            extraction fails.
        """
        pattern = self._COMPANY_PATTERNS.get(domain)
        if pattern:
            match = pattern.search(url)
            if match:
                slug = match.group(1)
                return slug.replace("-", " ").title()

        return "Unknown"
