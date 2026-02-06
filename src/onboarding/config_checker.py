"""Configuration checker for Job Radar."""

from pathlib import Path
from typing import Optional

import yaml


def get_project_root() -> Path:
    """Get the project root directory.

    Returns:
        Path to project root
    """
    # 3 levels up from this file
    return Path(__file__).parent.parent.parent


def is_configured(project_root: Optional[Path] = None) -> bool:
    """Check if Job Radar is properly configured.

    Args:
        project_root: Path to project root. Defaults to auto-detect.

    Returns:
        True if configured, False otherwise
    """
    missing = get_missing_config(project_root)
    return len(missing) == 0


def get_missing_config(project_root: Optional[Path] = None) -> list[str]:
    """Get list of missing configuration items.

    Args:
        project_root: Path to project root. Defaults to auto-detect.

    Returns:
        List of missing configuration descriptions
    """
    if project_root is None:
        project_root = get_project_root()

    missing = []

    # Check profile.yaml
    profile_path = project_root / "config" / "profile.yaml"
    if not profile_path.exists():
        missing.append("profile.yaml not found")
    else:
        # Check if profile has required values
        try:
            with open(profile_path) as f:
                profile = yaml.safe_load(f)

            if not profile:
                missing.append("profile.yaml is empty")
            else:
                # Check required fields
                if not profile.get("profile", {}).get("name"):
                    missing.append("User name not set in profile")

                if profile.get("profile", {}).get("name") == "Your Name":
                    missing.append("User name is still the default placeholder")

                titles = profile.get("target_titles", {}).get("primary", [])
                if not titles:
                    missing.append("No target job titles configured")

                keywords = profile.get("required_keywords", {}).get("primary", [])
                if not keywords:
                    missing.append("No search keywords configured")

        except yaml.YAMLError as e:
            missing.append(f"profile.yaml has invalid YAML: {e}")
        except Exception as e:
            missing.append(f"Error reading profile.yaml: {e}")

    # Check .env
    env_path = project_root / ".env"
    if not env_path.exists():
        missing.append(".env file not found")
    else:
        # .env exists — Slack is optional, so no webhook check here
        pass

    return missing


def get_config_status(project_root: Optional[Path] = None) -> dict:
    """Get detailed configuration status.

    Args:
        project_root: Path to project root. Defaults to auto-detect.

    Returns:
        Dictionary with configuration status details
    """
    if project_root is None:
        project_root = get_project_root()

    status = {
        "configured": False,
        "profile_exists": False,
        "profile_valid": False,
        "env_exists": False,
        "slack_configured": False,
        "gmail_configured": False,
        "missing": [],
        "user_name": None,
        "target_titles_count": 0,
        "keywords_count": 0,
    }

    # Check profile.yaml
    profile_path = project_root / "config" / "profile.yaml"
    status["profile_exists"] = profile_path.exists()

    if profile_path.exists():
        try:
            with open(profile_path) as f:
                profile = yaml.safe_load(f)

            if profile:
                name = profile.get("profile", {}).get("name", "")
                if name and name != "Your Name":
                    status["user_name"] = name

                titles = profile.get("target_titles", {}).get("primary", [])
                status["target_titles_count"] = len(titles)

                keywords = profile.get("required_keywords", {}).get("primary", [])
                status["keywords_count"] = len(keywords)

                # Profile is valid if it has name, titles, and keywords
                status["profile_valid"] = bool(
                    status["user_name"] and
                    status["target_titles_count"] > 0 and
                    status["keywords_count"] > 0
                )

        except Exception:
            pass

    # Check .env
    env_path = project_root / ".env"
    status["env_exists"] = env_path.exists()

    if env_path.exists():
        try:
            env_vars = _read_env(env_path)

            slack_url = env_vars.get("SLACK_WEBHOOK_URL", "")
            status["slack_configured"] = bool(
                slack_url and
                slack_url != "https://hooks.slack.com/services/XXX/YYY/ZZZ" and
                slack_url.startswith("https://hooks.slack.com/")
            )

            # Check Gmail (credentials.json must exist)
            creds_file = env_vars.get("GMAIL_CREDENTIALS_FILE", "credentials.json")
            creds_path = project_root / creds_file
            status["gmail_configured"] = creds_path.exists()

        except Exception:
            pass

    # Get missing items
    status["missing"] = get_missing_config(project_root)
    status["configured"] = len(status["missing"]) == 0

    return status


def _read_env(env_path: Path) -> dict:
    """Read .env file into dictionary.

    Args:
        env_path: Path to .env file

    Returns:
        Dictionary of environment variables
    """
    env = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env
