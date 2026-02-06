"""Pydantic validation models for Job Radar profile configuration."""

import re
from typing import Optional
from pydantic import BaseModel, Field, model_validator, field_validator


class ProfileInfo(BaseModel):
    """Basic profile information."""
    name: str = Field(min_length=1, description="User's full name")
    experience_years: int = Field(ge=0, le=50, default=5)
    layoff_date: Optional[str] = Field(default=None, description="Optional date for email filtering")
    remote_preference: bool = Field(default=True)


class TargetTitles(BaseModel):
    """Target job titles configuration."""
    primary: list[str] = Field(min_length=1, description="Must have at least one primary title")
    secondary: list[str] = Field(default_factory=list)

    @field_validator("primary", "secondary", mode="before")
    @classmethod
    def filter_empty_strings(cls, v):
        """Remove empty strings from lists."""
        if isinstance(v, list):
            return [item.strip() for item in v if item and item.strip()]
        return v


class RequiredKeywords(BaseModel):
    """Keywords for job matching."""
    primary: list[str] = Field(min_length=1, description="Must have at least one primary keyword")
    secondary: list[str] = Field(default_factory=list)

    @field_validator("primary", "secondary", mode="before")
    @classmethod
    def filter_empty_strings(cls, v):
        """Remove empty strings from lists."""
        if isinstance(v, list):
            return [item.strip() for item in v if item and item.strip()]
        return v


class Compensation(BaseModel):
    """Salary and compensation preferences."""
    min_salary: int = Field(ge=0, default=100000)
    max_salary: int = Field(ge=0, default=200000)
    flexible: bool = Field(default=True)
    currency: str = Field(default="USD")

    @model_validator(mode="after")
    def validate_salary_range(self):
        """Ensure min_salary is less than or equal to max_salary."""
        if self.min_salary > self.max_salary:
            raise ValueError("Minimum salary must be less than or equal to maximum salary")
        return self


class Location(BaseModel):
    """Location preferences."""
    remote_only: bool = Field(default=False)
    preferred: list[str] = Field(default_factory=lambda: ["Remote"])
    excluded: list[str] = Field(default_factory=list)

    @field_validator("preferred", "excluded", mode="before")
    @classmethod
    def filter_empty_strings(cls, v):
        """Remove empty strings from lists."""
        if isinstance(v, list):
            return [item.strip() for item in v if item and item.strip()]
        return v


class TargetCompanies(BaseModel):
    """Target companies by tier."""
    tier1: list[str] = Field(default_factory=list, description="Dream companies")
    tier2: list[str] = Field(default_factory=list, description="Great companies")
    tier3: list[str] = Field(default_factory=list, description="Good companies")

    @field_validator("tier1", "tier2", "tier3", mode="before")
    @classmethod
    def filter_empty_strings(cls, v):
        """Remove empty strings from lists."""
        if isinstance(v, list):
            return [item.strip() for item in v if item and item.strip()]
        return v


class Sources(BaseModel):
    """Job source configuration."""
    enabled: list[str] = Field(
        default_factory=lambda: [
            "indeed", "linkedin", "remoteok", "greenhouse", "lever", "hn_whoishiring"
        ]
    )
    disabled: list[str] = Field(default_factory=lambda: ["adzuna"])


class Scoring(BaseModel):
    """Scoring configuration."""
    title_match: float = Field(default=0.20)
    keyword_match: float = Field(default=0.40)
    company_tier: float = Field(default=0.15)
    salary_match: float = Field(default=0.05)
    remote_match: float = Field(default=0.05)
    min_notification_score: int = Field(ge=0, le=100, default=50)
    min_save_score: int = Field(ge=0, le=100, default=30)


class SlackNotifications(BaseModel):
    """Slack notification settings."""
    enabled: bool = Field(default=True)
    min_score: int = Field(ge=0, le=100, default=50)
    include_low_score: bool = Field(default=False)
    batch_mode: bool = Field(default=False)
    batch_interval_hours: int = Field(ge=1, default=4)


class EmailDigest(BaseModel):
    """Email digest settings."""
    enabled: bool = Field(default=False)
    frequency: str = Field(default="daily")
    send_time: str = Field(default="09:00")


class Notifications(BaseModel):
    """Notification configuration."""
    slack: SlackNotifications = Field(default_factory=SlackNotifications)
    email_digest: EmailDigest = Field(default_factory=EmailDigest)


class ProfileConfig(BaseModel):
    """Complete profile.yaml configuration."""
    profile: ProfileInfo
    target_titles: TargetTitles
    required_keywords: RequiredKeywords
    negative_keywords: list[str] = Field(default_factory=list)
    compensation: Compensation = Field(default_factory=Compensation)
    location: Location = Field(default_factory=Location)
    target_companies: TargetCompanies = Field(default_factory=TargetCompanies)
    sources: Sources = Field(default_factory=Sources)
    scoring: Scoring = Field(default_factory=Scoring)
    notifications: Notifications = Field(default_factory=Notifications)

    @field_validator("negative_keywords", mode="before")
    @classmethod
    def filter_empty_strings(cls, v):
        """Remove empty strings from lists."""
        if isinstance(v, list):
            return [item.strip() for item in v if item and item.strip()]
        return v


class EnvConfig(BaseModel):
    """Environment variable configuration."""
    slack_webhook_url: Optional[str] = Field(default=None)
    gmail_credentials_file: str = Field(default="credentials.json")
    gmail_token_file: str = Field(default="token.json")
    adzuna_app_id: Optional[str] = Field(default=None)
    adzuna_app_key: Optional[str] = Field(default=None)
    database_url: str = Field(default="sqlite:///data/job_radar.db")
    dashboard_port: int = Field(default=8501)
    job_check_interval_minutes: int = Field(default=30)
    email_check_interval_minutes: int = Field(default=15)

    @field_validator("slack_webhook_url")
    @classmethod
    def validate_slack_url(cls, v):
        """Validate Slack webhook URL format."""
        if v is None or v == "":
            return None
        if not v.startswith("https://hooks.slack.com/"):
            raise ValueError("Slack webhook URL must start with https://hooks.slack.com/")
        return v


def validate_profile(profile_dict: dict) -> ProfileConfig:
    """Validate a profile dictionary and return ProfileConfig.

    Args:
        profile_dict: Dictionary matching profile.yaml structure

    Returns:
        Validated ProfileConfig instance

    Raises:
        ValidationError: If validation fails
    """
    return ProfileConfig(**profile_dict)


def validate_env(env_dict: dict) -> EnvConfig:
    """Validate environment configuration.

    Args:
        env_dict: Dictionary of environment variables

    Returns:
        Validated EnvConfig instance

    Raises:
        ValidationError: If validation fails
    """
    return EnvConfig(**env_dict)
