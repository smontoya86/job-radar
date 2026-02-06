"""Email alert collector — parses job alert emails from Gmail."""
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from .base import BaseCollector, JobData


class EmailAlertCollector(BaseCollector):
    """Collector that parses job alert emails from LinkedIn, Google, Indeed, and Glassdoor."""

    name = "email_alerts"

    def __init__(self, alert_emails: list[dict]):
        """
        Initialize email alert collector.

        Args:
            alert_emails: List of raw email dicts with keys:
                - "html": HTML body of the email
                - "subject": Email subject line
                - "from_address": Sender email address
        """
        self.alert_emails = alert_emails

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """
        Parse job alert emails and extract job listings.

        Args:
            search_queries: Ignored — not applicable for email parsing.

        Returns:
            Deduplicated list of JobData objects extracted from alert emails.
        """
        all_jobs: list[JobData] = []

        for email in self.alert_emails:
            html = email.get("html", "")
            subject = email.get("subject", "")
            from_address = email.get("from_address", "")

            if not html:
                continue

            provider = self._detect_provider(from_address, subject)

            if provider == "linkedin":
                jobs = self._parse_linkedin_alert(html)
            elif provider == "google":
                jobs = self._parse_google_alert(html)
            elif provider == "indeed":
                jobs = self._parse_indeed_alert(html)
            elif provider == "glassdoor":
                # Glassdoor alerts share a similar structure to Indeed
                jobs = self._parse_generic_alert(html)
                for job in jobs:
                    job.source = "email_alert:glassdoor"
            else:
                jobs = self._parse_generic_alert(html)

            all_jobs.extend(jobs)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_jobs: list[JobData] = []
        for job in all_jobs:
            if job.url and job.url not in seen_urls:
                seen_urls.add(job.url)
                unique_jobs.append(job)
            elif not job.url:
                # Keep jobs without URLs (can't deduplicate them)
                unique_jobs.append(job)

        return unique_jobs

    def _detect_provider(self, from_address: str, subject: str) -> Optional[str]:
        """
        Detect the alert provider from sender address and subject line.

        Args:
            from_address: Sender email address.
            subject: Email subject line.

        Returns:
            Provider name ("linkedin", "google", "indeed", "glassdoor") or None.
        """
        from_lower = from_address.lower()
        subject_lower = subject.lower()

        # LinkedIn
        if from_lower == "jobs-noreply@linkedin.com" or (
            "linkedin" in from_lower
            and any(
                phrase in subject_lower
                for phrase in ["jobs you might be interested in", "new job"]
            )
        ):
            return "linkedin"

        # Google
        if from_lower == "noreply@google.com" and any(
            phrase in subject_lower for phrase in ["new jobs for", "jobs matching"]
        ):
            return "google"

        # Indeed
        if "indeed.com" in from_lower and any(
            phrase in subject_lower for phrase in ["new jobs", "jobs for"]
        ):
            return "indeed"

        # Glassdoor
        if "glassdoor.com" in from_lower and "new jobs" in subject_lower:
            return "glassdoor"

        return None

    def _parse_linkedin_alert(self, html: str) -> list[JobData]:
        """
        Parse a LinkedIn job alert email.

        Finds all <a> tags with hrefs containing 'linkedin.com/jobs/view/'
        and extracts job title from link text and company from surrounding context.

        Args:
            html: HTML body of the email.

        Returns:
            List of JobData extracted from the alert.
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobData] = []

        job_links = soup.find_all("a", href=re.compile(r"linkedin\.com/jobs/view/"))

        for link in job_links:
            href = link.get("href", "")
            title = link.get_text(strip=True)

            if not title:
                continue

            # Clean tracking parameters from URL
            clean_url = self._clean_url(href, "linkedin.com/jobs/view/")

            # Extract company from surrounding context
            company = self._extract_linkedin_company(link)

            # Extract location from surrounding context
            location = self._extract_nearby_text(link, "location")

            jobs.append(
                JobData(
                    title=title,
                    company=company,
                    url=clean_url,
                    source="email_alert:linkedin",
                    location=location,
                    description=None,
                    posted_date=None,
                    extra_data={"alert_type": "linkedin_email"},
                )
            )

        return jobs

    def _parse_google_alert(self, html: str) -> list[JobData]:
        """
        Parse a Google job alert email.

        Google alerts use structured HTML with job cards containing
        title, company, and location information.

        Args:
            html: HTML body of the email.

        Returns:
            List of JobData extracted from the alert.
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobData] = []

        # Google job alerts typically use table-based layouts with job cards
        # Look for links to Google job search results
        job_links = soup.find_all(
            "a", href=re.compile(r"google\.com/search\?.*|google\.com/about/jobs")
        )

        # Also look for structured job card patterns (divs or table rows)
        # Google alerts often structure jobs in table cells or div blocks
        job_cards = soup.find_all("tr")
        if not job_cards:
            job_cards = soup.find_all("div", recursive=True)

        processed_titles: set[str] = set()

        for link in job_links:
            href = link.get("href", "")
            title = link.get_text(strip=True)

            if not title or len(title) < 3 or title in processed_titles:
                continue

            processed_titles.add(title)

            # Walk up to the parent container to find company and location
            company, location = self._extract_google_card_details(link)

            jobs.append(
                JobData(
                    title=title,
                    company=company,
                    url=href,
                    source="email_alert:google",
                    location=location,
                    description=None,
                    posted_date=None,
                    extra_data={"alert_type": "google_email"},
                )
            )

        # If no links found via the standard pattern, try extracting from card structure
        if not jobs:
            jobs = self._extract_google_cards_from_structure(soup)

        return jobs

    def _parse_indeed_alert(self, html: str) -> list[JobData]:
        """
        Parse an Indeed job alert email.

        Finds job listing links containing 'indeed.com/viewjob'.

        Args:
            html: HTML body of the email.

        Returns:
            List of JobData extracted from the alert.
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobData] = []

        job_links = soup.find_all("a", href=re.compile(r"indeed\.com/viewjob"))

        for link in job_links:
            href = link.get("href", "")
            title = link.get_text(strip=True)

            if not title:
                continue

            # Clean tracking parameters from URL
            clean_url = self._clean_url(href, "indeed.com/viewjob")

            # Extract company from surrounding context
            company = self._extract_nearby_text(link, "company")
            location = self._extract_nearby_text(link, "location")

            jobs.append(
                JobData(
                    title=title,
                    company=company or "",
                    url=clean_url,
                    source="email_alert:indeed",
                    location=location,
                    description=None,
                    posted_date=None,
                    extra_data={"alert_type": "indeed_email"},
                )
            )

        return jobs

    def _parse_generic_alert(self, html: str) -> list[JobData]:
        """
        Fallback parser for unrecognized alert formats.

        Extracts any links that look like job postings based on URL patterns
        and surrounding text.

        Args:
            html: HTML body of the email.

        Returns:
            List of JobData extracted from the alert.
        """
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobData] = []

        # Common job URL patterns across various platforms
        job_url_patterns = re.compile(
            r"(linkedin\.com/jobs/view/"
            r"|indeed\.com/viewjob"
            r"|glassdoor\.com/job-listing/"
            r"|greenhouse\.io/.*?/jobs/"
            r"|lever\.co/.*?/"
            r"|boards\.greenhouse\.io/"
            r"|jobs\.ashbyhq\.com/"
            r"|careers\..+?/jobs/"
            r"|apply\.workable\.com/"
            r"|jobs\.smartrecruiters\.com/)",
            re.IGNORECASE,
        )

        all_links = soup.find_all("a", href=job_url_patterns)
        seen_urls: set[str] = set()

        for link in all_links:
            href = link.get("href", "")
            title = link.get_text(strip=True)

            if not title or len(title) < 3 or href in seen_urls:
                continue

            seen_urls.add(href)

            # Try to extract company from nearby context
            company = self._extract_nearby_text(link, "company")

            jobs.append(
                JobData(
                    title=title,
                    company=company or "",
                    url=href,
                    source="email_alert:unknown",
                    location=None,
                    description=None,
                    posted_date=None,
                    extra_data={"alert_type": "generic_email"},
                )
            )

        return jobs

    # ---- Helper methods ----

    def _clean_url(self, url: str, keep_pattern: str) -> str:
        """
        Clean tracking parameters from a URL while preserving the core path.

        Args:
            url: Full URL, possibly with tracking params.
            keep_pattern: Pattern that identifies the core part of the URL.

        Returns:
            Cleaned URL with tracking params stripped.
        """
        # Strip common email tracking redirects
        # Many alert emails wrap URLs in redirect links
        if "redirect" in url.lower() and keep_pattern in url:
            # Try to extract the actual job URL from the redirect
            match = re.search(
                rf"(https?://[^\s&]*{re.escape(keep_pattern)}[^\s&?]*)", url
            )
            if match:
                return match.group(1)

        # Remove common tracking query params but keep essential ones like job IDs
        if "?" in url:
            base, params_str = url.split("?", 1)
            essential_params = []
            for param in params_str.split("&"):
                param_lower = param.lower()
                # Keep job ID params, strip tracking params
                if any(
                    key in param_lower
                    for key in [
                        "gh_jid",
                        "jk=",
                        "jobid",
                        "job_id",
                        "id=",
                        "currentjobid",
                    ]
                ):
                    essential_params.append(param)
            if essential_params:
                return base + "?" + "&".join(essential_params)
            return base

        return url

    def _extract_linkedin_company(self, link_tag) -> str:
        """
        Extract company name from the context surrounding a LinkedIn job link.

        LinkedIn alerts typically place the company name in a sibling or
        nearby element after the job title link.

        Args:
            link_tag: BeautifulSoup Tag for the job link.

        Returns:
            Company name or empty string.
        """
        # Check immediate siblings
        for sibling in link_tag.next_siblings:
            if hasattr(sibling, "get_text"):
                text = sibling.get_text(strip=True)
                if text and len(text) > 1:
                    # LinkedIn often formats as "Company Name - Location"
                    parts = text.split(" - ")
                    if parts:
                        return parts[0].strip()
                    return text

        # Check parent container
        parent = link_tag.find_parent(["td", "div", "tr"])
        if parent:
            all_text = parent.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in all_text.split("\n") if line.strip()]
            # Company is usually the second non-empty line (after job title)
            title_text = link_tag.get_text(strip=True)
            for i, line in enumerate(lines):
                if line == title_text and i + 1 < len(lines):
                    company_line = lines[i + 1]
                    # Strip location suffix
                    parts = company_line.split(" - ")
                    if parts:
                        return parts[0].strip()
                    return company_line

        return ""

    def _extract_nearby_text(self, link_tag, field_type: str) -> Optional[str]:
        """
        Extract text from elements near a link tag.

        Looks for company or location information in siblings and parent containers.

        Args:
            link_tag: BeautifulSoup Tag for the job link.
            field_type: Type of field to extract ("company" or "location").

        Returns:
            Extracted text or None.
        """
        parent = link_tag.find_parent(["td", "div", "tr", "li"])
        if not parent:
            return None

        all_text = parent.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in all_text.split("\n") if line.strip()]
        title_text = link_tag.get_text(strip=True)

        # Filter out the title line
        non_title_lines = [line for line in lines if line != title_text]

        if field_type == "company" and non_title_lines:
            # Company is usually the first non-title text
            return non_title_lines[0]

        if field_type == "location" and len(non_title_lines) > 1:
            # Location is typically the second non-title text
            return non_title_lines[1]

        return None

    def _extract_google_card_details(self, link_tag) -> tuple[str, Optional[str]]:
        """
        Extract company and location from a Google job alert card.

        Google alerts structure data in table cells or nested divs
        around the job title link.

        Args:
            link_tag: BeautifulSoup Tag for the job title link.

        Returns:
            Tuple of (company, location).
        """
        company = ""
        location = None

        # Walk up to the containing card (typically a <tr> or <div>)
        card = link_tag.find_parent(["tr", "div", "td"])
        if not card:
            return company, location

        all_text = card.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in all_text.split("\n") if line.strip()]
        title_text = link_tag.get_text(strip=True)

        # Filter out the title and very short fragments
        info_lines = [
            line for line in lines if line != title_text and len(line) > 1
        ]

        if info_lines:
            company = info_lines[0]
        if len(info_lines) > 1:
            location = info_lines[1]

        return company, location

    def _extract_google_cards_from_structure(self, soup) -> list[JobData]:
        """
        Fallback: extract jobs from Google alert HTML structure.

        When standard link patterns don't match, look for repeated
        structural patterns (table rows or div groups) that contain
        job-like content.

        Args:
            soup: BeautifulSoup parsed HTML.

        Returns:
            List of JobData extracted from card structures.
        """
        jobs: list[JobData] = []

        # Look for any link that could be a job posting
        all_links = soup.find_all("a", href=True)

        for link in all_links:
            href = link.get("href", "")
            title = link.get_text(strip=True)

            # Skip non-job links (unsubscribe, preferences, logos, etc.)
            if not title or len(title) < 5:
                continue
            skip_patterns = ["unsubscribe", "preferences", "manage", "privacy", "terms"]
            if any(pattern in title.lower() for pattern in skip_patterns):
                continue
            if any(pattern in href.lower() for pattern in skip_patterns):
                continue

            # Only include links that look like they lead to job pages
            job_indicators = [
                "job",
                "career",
                "position",
                "opening",
                "apply",
                "hiring",
            ]
            if not any(
                indicator in href.lower() or indicator in title.lower()
                for indicator in job_indicators
            ):
                continue

            company, location = self._extract_google_card_details(link)

            jobs.append(
                JobData(
                    title=title,
                    company=company or "",
                    url=href,
                    source="email_alert:google",
                    location=location,
                    description=None,
                    posted_date=None,
                    extra_data={"alert_type": "google_email"},
                )
            )

        return jobs
