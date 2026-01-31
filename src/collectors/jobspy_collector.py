"""JobSpy collector for Indeed, LinkedIn, Glassdoor, Google Jobs."""
import asyncio
from datetime import datetime
from typing import Optional

from .base import BaseCollector, JobData


class JobSpyCollector(BaseCollector):
    """Collector using python-jobspy for multiple job boards."""

    name = "jobspy"

    def __init__(
        self,
        sites: Optional[list[str]] = None,
        country: str = "USA",
        results_wanted: int = 50,
        hours_old: int = 72,
    ):
        """
        Initialize JobSpy collector.

        Args:
            sites: List of sites to search. Options: indeed, linkedin, glassdoor, google
            country: Country to search in
            results_wanted: Number of results per search
            hours_old: Only return jobs posted within this many hours
        """
        self.sites = sites or ["indeed", "linkedin", "glassdoor"]
        self.country = country
        self.results_wanted = results_wanted
        self.hours_old = hours_old

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Collect jobs from JobSpy-supported sites."""
        # Import here to avoid issues if jobspy isn't installed
        try:
            from jobspy import scrape_jobs
        except ImportError:
            print("Warning: python-jobspy not installed. Skipping JobSpy collector.")
            return []

        all_jobs: list[JobData] = []

        for query in search_queries:
            try:
                # Run synchronous jobspy in executor
                loop = asyncio.get_event_loop()
                jobs_df = await loop.run_in_executor(
                    None,
                    lambda: scrape_jobs(
                        site_name=self.sites,
                        search_term=query,
                        location="Remote",
                        results_wanted=self.results_wanted,
                        hours_old=self.hours_old,
                        country_indeed=self.country,
                    ),
                )

                if jobs_df is None or jobs_df.empty:
                    continue

                # Convert DataFrame to JobData objects
                for _, row in jobs_df.iterrows():
                    job = self._row_to_job_data(row)
                    if job:
                        all_jobs.append(job)

            except Exception as e:
                print(f"JobSpy error for query '{query}': {e}")
                continue

        return all_jobs

    def _row_to_job_data(self, row) -> Optional[JobData]:
        """Convert a DataFrame row to JobData."""
        try:
            # Parse salary if available
            salary_min = None
            salary_max = None
            if "min_amount" in row and row["min_amount"]:
                try:
                    salary_min = int(float(row["min_amount"]))
                except (ValueError, TypeError):
                    pass
            if "max_amount" in row and row["max_amount"]:
                try:
                    salary_max = int(float(row["max_amount"]))
                except (ValueError, TypeError):
                    pass

            # Parse posted date
            posted_date = None
            if "date_posted" in row and row["date_posted"]:
                try:
                    if isinstance(row["date_posted"], datetime):
                        posted_date = row["date_posted"]
                    else:
                        posted_date = datetime.fromisoformat(str(row["date_posted"]))
                except (ValueError, TypeError):
                    pass

            # Determine if remote
            location = str(row.get("location", "")) if row.get("location") else None
            is_remote = bool(row.get("is_remote", False))
            if location and "remote" in location.lower():
                is_remote = True

            return JobData(
                title=str(row.get("title", "")),
                company=str(row.get("company", "")),
                url=str(row.get("job_url", "")),
                source=str(row.get("site", "jobspy")),
                location=location,
                description=str(row.get("description", "")) if row.get("description") else None,
                salary_min=salary_min,
                salary_max=salary_max,
                apply_url=str(row.get("job_url", "")),
                remote=is_remote,
                posted_date=posted_date,
            )
        except Exception as e:
            print(f"Error converting job row: {e}")
            return None
