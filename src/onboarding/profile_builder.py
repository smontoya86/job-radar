"""Profile builder for Job Radar configuration."""

from dataclasses import dataclass, field
from typing import Optional

from .validators import ProfileConfig, validate_profile


@dataclass
class ProfileBuilder:
    """Fluent builder for creating profile configurations.

    Usage:
        builder = ProfileBuilder()
        builder.set_name("John Doe")
        builder.set_target_titles(["Software Engineer", "Senior Engineer"])
        builder.set_keywords(["python", "backend"])
        config = builder.build()
    """

    # Basic profile
    name: str = ""
    experience_years: int = 5
    layoff_date: Optional[str] = None
    remote_preference: bool = True

    # Target titles
    target_titles_primary: list[str] = field(default_factory=list)
    target_titles_secondary: list[str] = field(default_factory=list)

    # Keywords
    keywords_primary: list[str] = field(default_factory=list)
    keywords_secondary: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=lambda: [
        "junior", "associate", "entry level", "entry-level",
        "intern", "internship", "contract", "contractor", "C2C"
    ])

    # Compensation
    salary_min: int = 100000
    salary_max: int = 200000
    salary_flexible: bool = True
    salary_currency: str = "USD"

    # Location
    remote_only: bool = False
    locations_preferred: list[str] = field(default_factory=lambda: ["Remote"])
    locations_excluded: list[str] = field(default_factory=list)

    # Target companies
    companies_tier1: list[str] = field(default_factory=list)
    companies_tier2: list[str] = field(default_factory=list)
    companies_tier3: list[str] = field(default_factory=list)

    # Sources
    sources_enabled: list[str] = field(default_factory=lambda: [
        "indeed", "linkedin", "remoteok", "greenhouse", "lever", "hn_whoishiring"
    ])
    sources_disabled: list[str] = field(default_factory=lambda: ["adzuna"])

    # Notifications
    slack_enabled: bool = True
    slack_min_score: int = 50
    slack_batch_mode: bool = False

    # Scoring
    min_notification_score: int = 50
    min_save_score: int = 30

    def set_name(self, name: str) -> "ProfileBuilder":
        """Set user name."""
        self.name = name
        return self

    def set_experience(self, years: int) -> "ProfileBuilder":
        """Set years of experience."""
        self.experience_years = years
        return self

    def set_layoff_date(self, date: Optional[str]) -> "ProfileBuilder":
        """Set layoff date for email filtering."""
        self.layoff_date = date
        return self

    def set_remote_preference(self, remote: bool) -> "ProfileBuilder":
        """Set remote work preference."""
        self.remote_preference = remote
        return self

    def set_target_titles(
        self,
        primary: list[str],
        secondary: Optional[list[str]] = None
    ) -> "ProfileBuilder":
        """Set target job titles."""
        self.target_titles_primary = primary
        self.target_titles_secondary = secondary or []
        return self

    def set_keywords(
        self,
        primary: list[str],
        secondary: Optional[list[str]] = None,
        negative: Optional[list[str]] = None
    ) -> "ProfileBuilder":
        """Set job matching keywords."""
        self.keywords_primary = primary
        self.keywords_secondary = secondary or []
        if negative is not None:
            self.negative_keywords = negative
        return self

    def set_salary_range(
        self,
        min_salary: int,
        max_salary: int,
        flexible: bool = True,
        currency: str = "USD"
    ) -> "ProfileBuilder":
        """Set salary range preferences."""
        self.salary_min = min_salary
        self.salary_max = max_salary
        self.salary_flexible = flexible
        self.salary_currency = currency
        return self

    def set_locations(
        self,
        preferred: list[str],
        excluded: Optional[list[str]] = None,
        remote_only: bool = False
    ) -> "ProfileBuilder":
        """Set location preferences."""
        self.locations_preferred = preferred
        self.locations_excluded = excluded or []
        self.remote_only = remote_only
        return self

    def set_target_companies(
        self,
        tier1: Optional[list[str]] = None,
        tier2: Optional[list[str]] = None,
        tier3: Optional[list[str]] = None
    ) -> "ProfileBuilder":
        """Set target companies by tier."""
        self.companies_tier1 = tier1 or []
        self.companies_tier2 = tier2 or []
        self.companies_tier3 = tier3 or []
        return self

    def set_sources(
        self,
        enabled: list[str],
        disabled: Optional[list[str]] = None
    ) -> "ProfileBuilder":
        """Set job sources."""
        self.sources_enabled = enabled
        self.sources_disabled = disabled or []
        return self

    def set_notifications(
        self,
        slack_enabled: bool = True,
        slack_min_score: int = 50,
        slack_batch_mode: bool = False
    ) -> "ProfileBuilder":
        """Set notification preferences."""
        self.slack_enabled = slack_enabled
        self.slack_min_score = slack_min_score
        self.slack_batch_mode = slack_batch_mode
        return self

    def set_scoring(
        self,
        min_notification_score: int = 50,
        min_save_score: int = 30
    ) -> "ProfileBuilder":
        """Set scoring thresholds."""
        self.min_notification_score = min_notification_score
        self.min_save_score = min_save_score
        return self

    def build(self) -> dict:
        """Build the profile configuration dictionary.

        Returns:
            Dictionary matching profile.yaml structure
        """
        return {
            "profile": {
                "name": self.name,
                "experience_years": self.experience_years,
                "layoff_date": self.layoff_date,
                "remote_preference": self.remote_preference,
            },
            "target_titles": {
                "primary": self.target_titles_primary,
                "secondary": self.target_titles_secondary,
            },
            "required_keywords": {
                "primary": self.keywords_primary,
                "secondary": self.keywords_secondary,
            },
            "negative_keywords": self.negative_keywords,
            "compensation": {
                "min_salary": self.salary_min,
                "max_salary": self.salary_max,
                "flexible": self.salary_flexible,
                "currency": self.salary_currency,
            },
            "location": {
                "remote_only": self.remote_only,
                "preferred": self.locations_preferred,
                "excluded": self.locations_excluded,
            },
            "target_companies": {
                "tier1": self.companies_tier1,
                "tier2": self.companies_tier2,
                "tier3": self.companies_tier3,
            },
            "sources": {
                "enabled": self.sources_enabled,
                "disabled": self.sources_disabled,
            },
            "scoring": {
                "title_match": 0.20,
                "keyword_match": 0.40,
                "company_tier": 0.15,
                "salary_match": 0.05,
                "remote_match": 0.05,
                "min_notification_score": self.min_notification_score,
                "min_save_score": self.min_save_score,
            },
            "notifications": {
                "slack": {
                    "enabled": self.slack_enabled,
                    "min_score": self.slack_min_score,
                    "include_low_score": False,
                    "batch_mode": self.slack_batch_mode,
                    "batch_interval_hours": 4,
                },
                "email_digest": {
                    "enabled": False,
                    "frequency": "daily",
                    "send_time": "09:00",
                },
            },
        }

    def validate(self) -> ProfileConfig:
        """Validate the current configuration.

        Returns:
            Validated ProfileConfig instance

        Raises:
            ValidationError: If validation fails
        """
        return validate_profile(self.build())

    def is_valid(self) -> tuple[bool, Optional[str]]:
        """Check if configuration is valid.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.validate()
            return True, None
        except Exception as e:
            return False, str(e)
