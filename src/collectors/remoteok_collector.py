"""RemoteOK.com job collector."""
import asyncio
from datetime import datetime
from typing import Optional

import aiohttp

from .base import BaseCollector, JobData


class RemoteOKCollector(BaseCollector):
    """Collector for RemoteOK.com jobs API."""

    name = "remoteok"
    API_URL = "https://remoteok.com/api"

    def __init__(self, timeout: int = 30):
        """
        Initialize RemoteOK collector.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from RemoteOK API."""
        all_jobs: list[JobData] = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={"User-Agent": "JobRadar/1.0"},
                ) as response:
                    if response.status != 200:
                        print(f"RemoteOK API returned status {response.status}")
                        return []

                    data = await response.json()

                    # First item is a legal notice, skip it
                    jobs = data[1:] if len(data) > 1 else []

                    # Filter by search queries
                    query_terms = [q.lower() for q in search_queries]

                    for job_data in jobs:
                        if self._matches_queries(job_data, query_terms):
                            job = self._parse_job(job_data)
                            if job:
                                all_jobs.append(job)

        except asyncio.TimeoutError:
            print("RemoteOK API timeout")
        except Exception as e:
            print(f"RemoteOK error: {e}")

        return all_jobs

    def _matches_queries(self, job_data: dict, query_terms: list[str]) -> bool:
        """Check if job matches any of the search queries."""
        # Combine searchable fields
        searchable = " ".join(
            [
                str(job_data.get("position", "")),
                str(job_data.get("company", "")),
                str(job_data.get("description", "")),
                " ".join(job_data.get("tags", [])),
            ]
        ).lower()

        # Check if any query term appears
        return any(term in searchable for term in query_terms)

    def _parse_job(self, data: dict) -> Optional[JobData]:
        """Parse RemoteOK job data to JobData."""
        try:
            # Parse salary
            salary_min = None
            salary_max = None
            if data.get("salary_min"):
                try:
                    salary_min = int(data["salary_min"])
                except (ValueError, TypeError):
                    pass
            if data.get("salary_max"):
                try:
                    salary_max = int(data["salary_max"])
                except (ValueError, TypeError):
                    pass

            # Parse date
            posted_date = None
            if data.get("date"):
                try:
                    # RemoteOK uses Unix timestamp
                    posted_date = datetime.fromtimestamp(int(data["epoch"]))
                except (ValueError, TypeError, KeyError):
                    try:
                        posted_date = datetime.fromisoformat(data["date"].replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

            # Build location from location field or tags
            location = data.get("location", "Remote")
            if not location or location == "":
                location = "Remote"

            return JobData(
                title=data.get("position", ""),
                company=data.get("company", ""),
                url=f"https://remoteok.com/remote-jobs/{data.get('slug', data.get('id', ''))}",
                source="remoteok",
                location=location,
                description=data.get("description", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                apply_url=data.get("apply_url") or data.get("url"),
                remote=True,  # RemoteOK is all remote jobs
                posted_date=posted_date,
                extra_data={"tags": data.get("tags", [])},
            )
        except Exception as e:
            print(f"Error parsing RemoteOK job: {e}")
            return None
