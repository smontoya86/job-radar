"""Greenhouse job board collector."""
import asyncio
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData


class GreenhouseCollector(BaseCollector):
    """Collector for Greenhouse job boards."""

    name = "greenhouse"

    # Popular tech companies using Greenhouse
    DEFAULT_COMPANIES = [
        # AI Companies (Tier 1)
        "openai",
        "anthropic",
        "perplexity",
        "cohere",
        "pinecone",
        "weaviate",
        "huggingface",
        "stability",
        "midjourney",
        "runway",
        "jasper",
        "grammarly",
        "writesonic",
        "copy-ai",
        # Big Tech
        "airbnb",
        "stripe",
        "figma",
        "notion",
        "discord",
        "pinterest",
        "reddit",
        "dropbox",
        "twitch",
        "databricks",
        "snowflake",
        "datadog",
        "hashicorp",
        "elastic",
        "confluent",
        "cockroachlabs",
        "mongodb",
        "gitlab",
        "postman",
        "retool",
        "airtable",
        "vercel",
        "linear",
        # Search/Discovery/Personalization
        "zillow",
        "redfin",
        "opendoor",
        "compass",
        "yelp",
        "tripadvisor",
        "expedia",
        "kayak",
        "hopper",
        "doordash",
        "instacart",
        "shipt",
        "gopuff",
        # EdTech (Search/Recommendations)
        "coursera",
        "duolingo",
        "chegg",
        "quizlet",
        "masterclass",
        "skillshare",
        "udemy",
        "khan-academy",
        # Enterprise/Productivity
        "atlassian",
        "asana",
        "monday",
        "clickup",
        "coda",
        "roam-research",
        "loom",
        "calendly",
        "typeform",
        "surveymonkey",
        # Ecommerce/Marketplace
        "etsy",
        "poshmark",
        "mercari",
        "offerup",
        "faire",
        "shopify",
        "bigcommerce",
        "bazaarvoice",
        # Fintech
        "sofi",
        "betterment",
        "wealthfront",
        "personal-capital",
        "nerdwallet",
        "creditkarma",
        # Health/Wellness
        "calm",
        "headspace",
        "noom",
        "peloton",
        "whoop",
        "oura",
        "strava",
        # Media/Content
        "medium",
        "substack",
        "spotify",
        "vimeo",
        "patreon",
        # Additional AI/ML
        "scale",
        "labelbox",
        "weights-and-biases",
        "dbt-labs",
        "hex",
        "deepgram",
        "assemblyai",
        "speechmatics",
        "rev",
    ]

    def __init__(
        self,
        companies: Optional[list[str]] = None,
        timeout: int = 30,
    ):
        """
        Initialize Greenhouse collector.

        Args:
            companies: List of company board tokens (e.g., "airbnb", "stripe")
            timeout: Request timeout in seconds
        """
        self.companies = companies or self.DEFAULT_COMPANIES
        self.timeout = timeout

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from Greenhouse boards."""
        all_jobs: list[JobData] = []
        query_terms = [q.lower() for q in search_queries]

        async with aiohttp.ClientSession() as session:
            # Fetch all companies concurrently
            tasks = [
                self._fetch_company_jobs(session, company)
                for company in self.companies
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for company_jobs in results:
                if isinstance(company_jobs, Exception):
                    continue
                for job in company_jobs:
                    if self._matches_queries(job, query_terms):
                        all_jobs.append(job)

        return all_jobs

    async def _fetch_company_jobs(
        self,
        session: aiohttp.ClientSession,
        company: str,
    ) -> list[JobData]:
        """Fetch jobs from a specific company's Greenhouse board."""
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"

        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                if response.status != 200:
                    return []

                data = await response.json()
                jobs = []

                for job_data in data.get("jobs", []):
                    job = self._parse_job(job_data, company)
                    if job:
                        jobs.append(job)

                # Fetch descriptions for PM-related jobs (to avoid too many API calls)
                pm_jobs = [j for j in jobs if self._is_pm_related(j.title)]
                if pm_jobs:
                    await self._fetch_descriptions(session, company, pm_jobs)

                return jobs

        except asyncio.TimeoutError:
            print(f"Greenhouse timeout for {company}")
            return []
        except Exception as e:
            print(f"Greenhouse error for {company}: {e}")
            return []

    def _is_pm_related(self, title: str) -> bool:
        """Check if job title is PM-related (to limit description fetches)."""
        title_lower = title.lower()
        pm_terms = ["product manager", "product lead", "product director", "pm", "product"]
        return any(term in title_lower for term in pm_terms)

    async def _fetch_descriptions(
        self,
        session: aiohttp.ClientSession,
        company: str,
        jobs: list[JobData],
    ) -> None:
        """Fetch full descriptions for jobs (modifies jobs in place)."""
        import re
        from bs4 import BeautifulSoup

        for job in jobs:
            try:
                # Extract job ID from URL query param or extra_data
                job_id = None
                if job.url:
                    # URL format: https://company.com/jobs/search?gh_jid=12345
                    if "gh_jid=" in job.url:
                        job_id = job.url.split("gh_jid=")[-1].split("&")[0]
                    else:
                        # Fallback: try last path segment
                        job_id = job.url.rstrip("/").split("/")[-1]

                # Also check extra_data for job_id
                if not job_id and job.extra_data and "job_id" in job.extra_data:
                    job_id = job.extra_data["job_id"]

                if not job_id or not job_id.isdigit():
                    continue

                url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"

                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        continue

                    data = await response.json()
                    content = data.get("content", "")

                    if content:
                        # Content is HTML-encoded, decode first then strip tags
                        import html
                        decoded_content = html.unescape(content)
                        soup = BeautifulSoup(decoded_content, "html.parser")
                        job.description = soup.get_text(separator=" ", strip=True)

            except Exception as e:
                # Silently continue on error - description fetching is best-effort
                pass

    def _matches_queries(self, job: JobData, query_terms: list[str]) -> bool:
        """Check if job matches any search queries."""
        searchable = " ".join(
            [
                job.title,
                job.company,
                job.description or "",
                job.location or "",
            ]
        ).lower()

        return any(term in searchable for term in query_terms)

    def _parse_job(self, data: dict, company_slug: str) -> Optional[JobData]:
        """Parse Greenhouse job data to JobData."""
        try:
            # Get location
            location = None
            if data.get("location"):
                location = data["location"].get("name")

            # Determine if remote
            is_remote = False
            if location:
                is_remote = any(
                    term in location.lower()
                    for term in ["remote", "anywhere", "worldwide"]
                )

            # Parse date
            posted_date = None
            if data.get("updated_at"):
                try:
                    posted_date = datetime.fromisoformat(
                        data["updated_at"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Get company name (capitalize slug)
            company_name = company_slug.replace("-", " ").title()

            return JobData(
                title=data.get("title", ""),
                company=company_name,
                url=data.get("absolute_url", ""),
                source="greenhouse",
                location=location,
                description=None,  # Fetched separately via _fetch_descriptions
                salary_min=None,
                salary_max=None,
                apply_url=data.get("absolute_url"),
                remote=is_remote,
                posted_date=posted_date,
                extra_data={
                    "job_id": str(data.get("id", "")),  # Store job ID for description fetch
                    "departments": [d.get("name") for d in data.get("departments", [])],
                    "offices": [o.get("name") for o in data.get("offices", [])],
                },
            )
        except Exception as e:
            print(f"Error parsing Greenhouse job: {e}")
            return None
