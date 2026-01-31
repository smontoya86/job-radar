"""Application settings using Pydantic."""
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="sqlite:///job_radar.db",
        description="SQLAlchemy database URL",
    )

    # Slack
    slack_webhook_url: Optional[str] = Field(
        default=None,
        description="Slack webhook URL for notifications",
    )

    # Gmail
    gmail_credentials_file: str = Field(
        default="credentials.json",
        description="Path to Gmail OAuth credentials file",
    )
    gmail_token_file: str = Field(
        default="token.json",
        description="Path to Gmail OAuth token file",
    )

    # Adzuna API (optional)
    adzuna_app_id: Optional[str] = Field(
        default=None,
        description="Adzuna API app ID",
    )
    adzuna_app_key: Optional[str] = Field(
        default=None,
        description="Adzuna API key",
    )

    # Dashboard
    dashboard_port: int = Field(
        default=8501,
        description="Streamlit dashboard port",
    )

    # Scheduler intervals
    job_check_interval_minutes: int = Field(
        default=30,
        description="How often to check for new jobs (minutes)",
    )
    email_check_interval_minutes: int = Field(
        default=15,
        description="How often to check Gmail for new emails (minutes)",
    )

    # Paths
    config_dir: Path = Field(
        default=Path(__file__).parent,
        description="Configuration directory",
    )

    @property
    def profile_path(self) -> Path:
        """Path to the profile.yaml file."""
        return self.config_dir / "profile.yaml"

    @property
    def project_root(self) -> Path:
        """Project root directory."""
        return self.config_dir.parent


# Global settings instance
settings = Settings()
