"""SmartRecruiters job board collector."""
import asyncio
import random
from datetime import datetime
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseCollector, JobData


class SmartRecruitersCollector(BaseCollector):
    """Collector for SmartRecruiters public job postings API."""

    name = "smartrecruiters"

    # Companies using SmartRecruiters for their career sites
    DEFAULT_COMPANIES = [
        "visa",
        "bosch",
        "samsungsdsa",
        "skyscanner",
        "groupon",
        "avery-dennison",
        "equinix",
        "jll",
        "publicissapient",
        "docusign",
    ]

    def __init__(
        self,
        companies: Optional[list[str]] = None,
        timeout: int = 30,
        max_concurrent: int = 3,
        delay_between_requests: tuple[float, float] = (1.0, 2.5),
    ):
        """
        Initialize SmartRecruiters collector.

        Args:
            companies: List of SmartRecruiters company identifiers
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent requests (rate limiting)
            delay_between_requests: Min/max seconds delay between requests
        """
        self.companies = companies or self.DEFAULT_COMPANIES
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.delay_range = delay_between_requests

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from SmartRecruiters postings API."""
        all_jobs: list[JobData] = []

        # Use semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def fetch_with_rate_limit(
            company: str, query: str
        ) -> list[JobData]:
            async with semaphore:
                delay = random.uniform(*self.delay_range)
                await asyncio.sleep(delay)
                return await self._fetch_company_jobs(
                    session, company, query
                )

        async with aiohttp.ClientSession() as session:
            tasks = [
                fetch_with_rate_limit(company, query)
                for company in self.companies
                for query in search_queries
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            seen_urls: set[str] = set()
            for company_jobs in results:
                if isinstance(company_jobs, Exception):
                    continue
                for job in company_jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)

        return all_jobs

    async def _fetch_company_jobs(
        self,
        session: aiohttp.ClientSession,
        company: str,
        query: str,
    ) -> list[JobData]:
        """Fetch jobs from a specific company's SmartRecruiters postings."""
        url = (
            f"https://api.smartrecruiters.com/v1/companies"
            f"/{company}/postings"
        )
        params = {
            "q": query,
            "limit": 20,
        }

        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    return []

                data = await response.json()
                jobs = []

                for posting in data.get("content", []):
                    job = await self._parse_posting(
                        session, company, posting
                    )
                    if job:
                        jobs.append(job)

                return jobs

        except asyncio.TimeoutError:
            print(f"SmartRecruiters timeout for {company}")
            return []
        except Exception as e:
            print(f"SmartRecruiters error for {company}: {e}")
            return []

    async def _parse_posting(
        self,
        session: aiohttp.ClientSession,
        company_slug: str,
        posting: dict,
    ) -> Optional[JobData]:
        """Parse a SmartRecruiters posting into JobData."""
        try:
            posting_id = posting.get("id", "")
            title = posting.get("name", "")
            if not title or not posting_id:
                return None

            # Company name from the posting data
            company_data = posting.get("company", {})
            company_name = company_data.get("name", "")
            if not company_name:
                company_name = company_slug.replace("-", " ").title()

            # Location
            location_data = posting.get("location", {})
            location_parts = []
            if location_data.get("city"):
                location_parts.append(location_data["city"])
            if location_data.get("region"):
                location_parts.append(location_data["region"])
            if location_data.get("country"):
                location_parts.append(location_data["country"])
            location = ", ".join(location_parts) if location_parts else None

            # Determine if remote
            is_remote = False
            if location:
                is_remote = any(
                    term in location.lower()
                    for term in ["remote", "anywhere", "worldwide"]
                )

            # Parse released date
            posted_date = None
            released_date = posting.get("releasedDate")
            if released_date:
                try:
                    posted_date = datetime.fromisoformat(
                        released_date.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Build the public job URL
            job_url = (
                f"https://jobs.smartrecruiters.com"
                f"/{company_slug}/{posting_id}"
            )

            # Fetch full description from the detail endpoint
            description = await self._fetch_description(
                session, company_slug, posting_id
            )

            return JobData(
                title=title,
                company=company_name,
                url=job_url,
                source="smartrecruiters",
                location=location,
                description=description,
                salary_min=None,
                salary_max=None,
                apply_url=job_url,
                remote=is_remote,
                posted_date=posted_date,
                extra_data={
                    "posting_id": posting_id,
                    "company_slug": company_slug,
                },
            )
        except Exception as e:
            print(f"Error parsing SmartRecruiters posting: {e}")
            return None

    async def _fetch_description(
        self,
        session: aiohttp.ClientSession,
        company_slug: str,
        posting_id: str,
    ) -> Optional[str]:
        """Fetch full job description from the posting detail endpoint."""
        url = (
            f"https://api.smartrecruiters.com/v1/companies"
            f"/{company_slug}/postings/{posting_id}"
        )

        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()

                # Description is nested under jobAd.sections.jobDescription.text
                job_ad = data.get("jobAd", {})
                sections = job_ad.get("sections", {})
                job_desc = sections.get("jobDescription", {})
                html_text = job_desc.get("text", "")

                if html_text:
                    soup = BeautifulSoup(html_text, "html.parser")
                    return soup.get_text(separator=" ", strip=True)

                return None

        except Exception:
            # Description fetching is best-effort
            return None
