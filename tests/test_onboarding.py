"""Tests for onboarding module."""
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.onboarding.validators import (
    ProfileConfig,
    ProfileInfo,
    TargetTitles,
    RequiredKeywords,
    Compensation,
    Location,
    TargetCompanies,
    EnvConfig,
    validate_profile,
    validate_env,
)
from src.onboarding.profile_builder import ProfileBuilder
from src.onboarding.config_writer import ConfigWriter
from src.onboarding.config_checker import (
    is_configured,
    get_missing_config,
    get_config_status,
)


class TestValidators:
    """Tests for Pydantic validation models."""

    def test_profile_info_valid(self):
        """Test valid profile info."""
        info = ProfileInfo(
            name="John Doe",
            experience_years=5,
            remote_preference=True,
        )
        assert info.name == "John Doe"
        assert info.experience_years == 5

    def test_profile_info_empty_name_fails(self):
        """Test that empty name fails validation."""
        with pytest.raises(ValueError):
            ProfileInfo(name="", experience_years=5)

    def test_profile_info_experience_range(self):
        """Test experience years must be in valid range."""
        # Valid
        ProfileInfo(name="Test", experience_years=0)
        ProfileInfo(name="Test", experience_years=50)

        # Invalid - negative
        with pytest.raises(ValueError):
            ProfileInfo(name="Test", experience_years=-1)

        # Invalid - too high
        with pytest.raises(ValueError):
            ProfileInfo(name="Test", experience_years=51)

    def test_target_titles_valid(self):
        """Test valid target titles."""
        titles = TargetTitles(
            primary=["Software Engineer", "Senior Engineer"],
            secondary=["Backend Engineer"],
        )
        assert len(titles.primary) == 2
        assert len(titles.secondary) == 1

    def test_target_titles_requires_primary(self):
        """Test that at least one primary title is required."""
        with pytest.raises(ValueError):
            TargetTitles(primary=[], secondary=["Backend Engineer"])

    def test_target_titles_filters_empty_strings(self):
        """Test that empty strings are filtered from lists."""
        titles = TargetTitles(
            primary=["Engineer", "", "  ", "PM"],
            secondary=["", "Designer"],
        )
        assert titles.primary == ["Engineer", "PM"]
        assert titles.secondary == ["Designer"]

    def test_required_keywords_valid(self):
        """Test valid required keywords."""
        keywords = RequiredKeywords(
            primary=["python", "backend"],
            secondary=["kubernetes"],
        )
        assert len(keywords.primary) == 2

    def test_required_keywords_requires_primary(self):
        """Test that at least one primary keyword is required."""
        with pytest.raises(ValueError):
            RequiredKeywords(primary=[], secondary=["bonus"])

    def test_compensation_valid(self):
        """Test valid compensation range."""
        comp = Compensation(
            min_salary=150000,
            max_salary=250000,
            flexible=True,
        )
        assert comp.min_salary == 150000
        assert comp.max_salary == 250000

    def test_compensation_min_cannot_exceed_max(self):
        """Test that min salary cannot exceed max salary."""
        with pytest.raises(ValueError):
            Compensation(min_salary=300000, max_salary=200000)

    def test_compensation_equal_valid(self):
        """Test that equal min/max is valid."""
        comp = Compensation(min_salary=200000, max_salary=200000)
        assert comp.min_salary == comp.max_salary

    def test_location_valid(self):
        """Test valid location preferences."""
        loc = Location(
            remote_only=True,
            preferred=["Remote", "San Francisco"],
            excluded=["India"],
        )
        assert loc.remote_only is True
        assert len(loc.preferred) == 2

    def test_location_filters_empty_strings(self):
        """Test that empty strings are filtered from location lists."""
        loc = Location(
            preferred=["Remote", "", "NYC"],
            excluded=["", ""],
        )
        assert loc.preferred == ["Remote", "NYC"]
        assert loc.excluded == []

    def test_target_companies_valid(self):
        """Test valid target companies."""
        companies = TargetCompanies(
            tier1=["Google", "Meta"],
            tier2=["Stripe"],
            tier3=[],
        )
        assert len(companies.tier1) == 2
        assert len(companies.tier2) == 1
        assert len(companies.tier3) == 0

    def test_env_config_valid(self):
        """Test valid environment config."""
        env = EnvConfig(
            slack_webhook_url="https://hooks.slack.com/services/T123/B456/abc",
            database_url="sqlite:///test.db",
        )
        assert env.slack_webhook_url.startswith("https://hooks.slack.com/")

    def test_env_config_invalid_slack_url(self):
        """Test that invalid Slack URL fails validation."""
        with pytest.raises(ValueError):
            EnvConfig(slack_webhook_url="https://invalid.com/webhook")

    def test_env_config_empty_slack_allowed(self):
        """Test that empty/None Slack URL is allowed."""
        env = EnvConfig(slack_webhook_url=None)
        assert env.slack_webhook_url is None

        env2 = EnvConfig(slack_webhook_url="")
        assert env2.slack_webhook_url is None

    def test_full_profile_config_valid(self):
        """Test valid full profile configuration."""
        config = ProfileConfig(
            profile=ProfileInfo(name="Test User", experience_years=5),
            target_titles=TargetTitles(primary=["Engineer"]),
            required_keywords=RequiredKeywords(primary=["python"]),
            negative_keywords=["junior"],
            compensation=Compensation(min_salary=100000, max_salary=200000),
            location=Location(preferred=["Remote"]),
        )
        assert config.profile.name == "Test User"

    def test_validate_profile_function(self):
        """Test validate_profile helper function."""
        profile_dict = {
            "profile": {"name": "Test", "experience_years": 3},
            "target_titles": {"primary": ["PM"], "secondary": []},
            "required_keywords": {"primary": ["AI"], "secondary": []},
            "negative_keywords": [],
        }
        config = validate_profile(profile_dict)
        assert config.profile.name == "Test"


class TestProfileBuilder:
    """Tests for ProfileBuilder class."""

    def test_builder_defaults(self):
        """Test builder with default values."""
        builder = ProfileBuilder()
        assert builder.name == ""
        assert builder.experience_years == 5
        assert builder.remote_preference is True

    def test_builder_fluent_interface(self):
        """Test fluent builder interface."""
        builder = (
            ProfileBuilder()
            .set_name("John Doe")
            .set_experience(10)
            .set_remote_preference(False)
        )
        assert builder.name == "John Doe"
        assert builder.experience_years == 10
        assert builder.remote_preference is False

    def test_builder_set_target_titles(self):
        """Test setting target titles."""
        builder = ProfileBuilder()
        builder.set_target_titles(
            primary=["Engineer", "Senior Engineer"],
            secondary=["Staff Engineer"],
        )
        assert len(builder.target_titles_primary) == 2
        assert len(builder.target_titles_secondary) == 1

    def test_builder_set_keywords(self):
        """Test setting keywords."""
        builder = ProfileBuilder()
        builder.set_keywords(
            primary=["python", "backend"],
            secondary=["kubernetes"],
            negative=["junior", "intern"],
        )
        assert len(builder.keywords_primary) == 2
        assert len(builder.keywords_secondary) == 1
        assert len(builder.negative_keywords) == 2

    def test_builder_set_salary_range(self):
        """Test setting salary range."""
        builder = ProfileBuilder()
        builder.set_salary_range(150000, 250000, flexible=True)
        assert builder.salary_min == 150000
        assert builder.salary_max == 250000
        assert builder.salary_flexible is True

    def test_builder_set_locations(self):
        """Test setting locations."""
        builder = ProfileBuilder()
        builder.set_locations(
            preferred=["Remote", "NYC"],
            excluded=["India"],
            remote_only=True,
        )
        assert len(builder.locations_preferred) == 2
        assert len(builder.locations_excluded) == 1
        assert builder.remote_only is True

    def test_builder_set_target_companies(self):
        """Test setting target companies."""
        builder = ProfileBuilder()
        builder.set_target_companies(
            tier1=["Google", "Meta"],
            tier2=["Stripe"],
            tier3=["Spotify"],
        )
        assert len(builder.companies_tier1) == 2
        assert len(builder.companies_tier2) == 1
        assert len(builder.companies_tier3) == 1

    def test_builder_build(self):
        """Test building profile dictionary."""
        builder = ProfileBuilder()
        builder.set_name("Test User")
        builder.set_target_titles(primary=["Engineer"])
        builder.set_keywords(primary=["python"])

        config = builder.build()

        assert config["profile"]["name"] == "Test User"
        assert config["target_titles"]["primary"] == ["Engineer"]
        assert config["required_keywords"]["primary"] == ["python"]

    def test_builder_validate_success(self):
        """Test validation of valid configuration."""
        builder = ProfileBuilder()
        builder.set_name("Test User")
        builder.set_target_titles(primary=["Engineer"])
        builder.set_keywords(primary=["python"])

        config = builder.validate()
        assert config.profile.name == "Test User"

    def test_builder_validate_failure(self):
        """Test validation fails for invalid configuration."""
        builder = ProfileBuilder()
        # Name not set, titles not set
        is_valid, error = builder.is_valid()
        assert is_valid is False
        assert error is not None

    def test_builder_is_valid(self):
        """Test is_valid helper method."""
        builder = ProfileBuilder()
        builder.set_name("Test")
        builder.set_target_titles(primary=["PM"])
        builder.set_keywords(primary=["AI"])

        is_valid, error = builder.is_valid()
        assert is_valid is True
        assert error is None


class TestConfigWriter:
    """Tests for ConfigWriter class."""

    def test_write_profile(self):
        """Test writing profile.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ConfigWriter(Path(tmpdir))

            builder = ProfileBuilder()
            builder.set_name("Test User")
            builder.set_target_titles(primary=["Engineer"])
            builder.set_keywords(primary=["python"])

            profile_path = writer.write_profile(builder.build(), backup=False)

            assert profile_path.exists()

            # Verify content
            with open(profile_path) as f:
                content = f.read()
            assert "Test User" in content
            assert "Engineer" in content

    def test_write_profile_creates_directory(self):
        """Test that config directory is created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "subdir"
            writer = ConfigWriter(project_root)

            builder = ProfileBuilder()
            builder.set_name("Test")
            builder.set_target_titles(primary=["PM"])
            builder.set_keywords(primary=["AI"])

            profile_path = writer.write_profile(builder.build(), backup=False)

            assert profile_path.exists()
            assert profile_path.parent.name == "config"

    def test_write_profile_backup(self):
        """Test that existing profile is backed up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ConfigWriter(Path(tmpdir))

            # Write initial profile
            builder = ProfileBuilder()
            builder.set_name("First")
            builder.set_target_titles(primary=["PM"])
            builder.set_keywords(primary=["AI"])
            writer.write_profile(builder.build(), backup=False)

            # Write second profile with backup
            builder.set_name("Second")
            writer.write_profile(builder.build(), backup=True)

            # Check backup exists
            backup_files = list(Path(tmpdir).glob("config/*.bak"))
            assert len(backup_files) == 1

    def test_write_env(self):
        """Test writing .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ConfigWriter(Path(tmpdir))

            env_dict = {
                "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T123/B456/abc",
                "DATABASE_URL": "sqlite:///test.db",
            }

            env_path = writer.write_env(env_dict, backup=False)

            assert env_path.exists()

            # Verify content
            with open(env_path) as f:
                content = f.read()
            assert "SLACK_WEBHOOK_URL=" in content
            assert "T123/B456/abc" in content

    def test_write_env_updates_slack_url(self):
        """Test that .env updates Slack webhook URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ConfigWriter(Path(tmpdir))

            # Write env with Slack webhook
            env_config = {
                "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T123/B456/abc",
            }
            writer.write_env(env_config, backup=False)

            # Read and verify
            with open(writer.env_path) as f:
                content = f.read()

            assert "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T123/B456/abc" in content

    def test_write_profile_yaml_format(self):
        """Test that written profile is valid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ConfigWriter(Path(tmpdir))

            builder = ProfileBuilder()
            builder.set_name("Test User")
            builder.set_target_titles(primary=["Engineer", "PM"])
            builder.set_keywords(
                primary=["python", "backend"],
                secondary=["kubernetes"],
                negative=["junior"],
            )
            builder.set_salary_range(150000, 250000)
            builder.set_target_companies(
                tier1=["Google"],
                tier2=["Stripe"],
            )

            profile_path = writer.write_profile(builder.build(), backup=False)

            # Verify it's valid YAML
            with open(profile_path) as f:
                parsed = yaml.safe_load(f)

            assert parsed["profile"]["name"] == "Test User"
            assert "Engineer" in parsed["target_titles"]["primary"]


class TestConfigChecker:
    """Tests for config checker functions."""

    def test_is_configured_true(self):
        """Test is_configured returns True when properly configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create valid profile.yaml
            config_dir = project_root / "config"
            config_dir.mkdir()
            profile = {
                "profile": {"name": "Test User", "experience_years": 5},
                "target_titles": {"primary": ["Engineer"]},
                "required_keywords": {"primary": ["python"]},
            }
            with open(config_dir / "profile.yaml", "w") as f:
                yaml.dump(profile, f)

            # Create valid .env
            with open(project_root / ".env", "w") as f:
                f.write("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T123/B456/abc\n")

            assert is_configured(project_root) is True

    def test_is_configured_false_no_profile(self):
        """Test is_configured returns False when profile.yaml missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Only create .env
            with open(project_root / ".env", "w") as f:
                f.write("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T123/B456/abc\n")

            assert is_configured(project_root) is False

    def test_is_configured_false_no_env(self):
        """Test is_configured returns False when .env missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create valid profile.yaml
            config_dir = project_root / "config"
            config_dir.mkdir()
            profile = {
                "profile": {"name": "Test User"},
                "target_titles": {"primary": ["Engineer"]},
                "required_keywords": {"primary": ["python"]},
            }
            with open(config_dir / "profile.yaml", "w") as f:
                yaml.dump(profile, f)

            assert is_configured(project_root) is False

    def test_is_configured_false_placeholder_name(self):
        """Test is_configured returns False when name is placeholder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create profile with placeholder name
            config_dir = project_root / "config"
            config_dir.mkdir()
            profile = {
                "profile": {"name": "Your Name"},
                "target_titles": {"primary": ["Engineer"]},
                "required_keywords": {"primary": ["python"]},
            }
            with open(config_dir / "profile.yaml", "w") as f:
                yaml.dump(profile, f)

            with open(project_root / ".env", "w") as f:
                f.write("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T123/B456/abc\n")

            assert is_configured(project_root) is False

    def test_is_configured_true_placeholder_webhook(self):
        """Test is_configured returns True even when webhook is placeholder (Slack is optional)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create valid profile
            config_dir = project_root / "config"
            config_dir.mkdir()
            profile = {
                "profile": {"name": "Test User"},
                "target_titles": {"primary": ["Engineer"]},
                "required_keywords": {"primary": ["python"]},
            }
            with open(config_dir / "profile.yaml", "w") as f:
                yaml.dump(profile, f)

            # Placeholder webhook
            with open(project_root / ".env", "w") as f:
                f.write("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ\n")

            assert is_configured(project_root) is True

    def test_is_configured_true_without_slack(self):
        """Test is_configured returns True with valid profile + .env but no Slack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create valid profile
            config_dir = project_root / "config"
            config_dir.mkdir()
            profile = {
                "profile": {"name": "Test User"},
                "target_titles": {"primary": ["Engineer"]},
                "required_keywords": {"primary": ["python"]},
            }
            with open(config_dir / "profile.yaml", "w") as f:
                yaml.dump(profile, f)

            # .env with no Slack webhook at all
            with open(project_root / ".env", "w") as f:
                f.write("DATABASE_URL=sqlite:///test.db\n")

            assert is_configured(project_root) is True

    def test_get_missing_config_detailed(self):
        """Test get_missing_config returns specific missing items."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            missing = get_missing_config(project_root)

            assert len(missing) > 0
            assert any("profile.yaml" in m for m in missing)
            assert any(".env" in m for m in missing)

    def test_get_missing_config_no_titles(self):
        """Test detection of missing job titles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            config_dir = project_root / "config"
            config_dir.mkdir()
            profile = {
                "profile": {"name": "Test User"},
                "target_titles": {"primary": []},  # Empty!
                "required_keywords": {"primary": ["python"]},
            }
            with open(config_dir / "profile.yaml", "w") as f:
                yaml.dump(profile, f)

            with open(project_root / ".env", "w") as f:
                f.write("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T123/B456/abc\n")

            missing = get_missing_config(project_root)

            assert any("title" in m.lower() for m in missing)

    def test_get_config_status_complete(self):
        """Test get_config_status with complete configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create valid profile
            config_dir = project_root / "config"
            config_dir.mkdir()
            profile = {
                "profile": {"name": "Test User"},
                "target_titles": {"primary": ["Engineer", "PM"]},
                "required_keywords": {"primary": ["python", "AI"]},
            }
            with open(config_dir / "profile.yaml", "w") as f:
                yaml.dump(profile, f)

            with open(project_root / ".env", "w") as f:
                f.write("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T123/B456/abc\n")

            status = get_config_status(project_root)

            assert status["configured"] is True
            assert status["profile_exists"] is True
            assert status["profile_valid"] is True
            assert status["slack_configured"] is True
            assert status["user_name"] == "Test User"
            assert status["target_titles_count"] == 2
            assert status["keywords_count"] == 2
            assert len(status["missing"]) == 0

    def test_get_config_status_partial(self):
        """Test get_config_status with partial configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Profile exists but with placeholder name
            config_dir = project_root / "config"
            config_dir.mkdir()
            profile = {
                "profile": {"name": "Your Name"},
                "target_titles": {"primary": ["Engineer"]},
                "required_keywords": {"primary": ["python"]},
            }
            with open(config_dir / "profile.yaml", "w") as f:
                yaml.dump(profile, f)

            status = get_config_status(project_root)

            assert status["configured"] is False
            assert status["profile_exists"] is True
            assert status["profile_valid"] is False
            assert status["env_exists"] is False
            assert status["user_name"] is None  # Placeholder doesn't count


class TestIntegration:
    """Integration tests for the full onboarding flow."""

    def test_full_onboarding_flow(self):
        """Test complete flow: build -> validate -> write -> check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Step 1: Build configuration
            builder = ProfileBuilder()
            builder.set_name("Integration Test User")
            builder.set_experience(7)
            builder.set_remote_preference(True)
            builder.set_target_titles(
                primary=["Software Engineer", "Senior Engineer"],
                secondary=["Backend Engineer"],
            )
            builder.set_keywords(
                primary=["python", "backend", "distributed systems"],
                secondary=["kubernetes", "docker"],
                negative=["junior", "intern"],
            )
            builder.set_salary_range(175000, 275000, flexible=True)
            builder.set_locations(
                preferred=["Remote", "San Francisco", "New York"],
                excluded=["India"],
                remote_only=False,
            )
            builder.set_target_companies(
                tier1=["Google", "Meta", "Apple"],
                tier2=["Stripe", "Airbnb"],
                tier3=["Spotify", "Pinterest"],
            )

            # Step 2: Validate configuration
            is_valid, error = builder.is_valid()
            assert is_valid is True, f"Validation failed: {error}"

            # Step 3: Write configuration files
            writer = ConfigWriter(project_root)
            profile_path = writer.write_profile(builder.build(), backup=False)
            env_path = writer.write_env({
                "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T123/B456/abc",
            }, backup=False)

            assert profile_path.exists()
            assert env_path.exists()

            # Step 4: Verify configuration is recognized as complete
            assert is_configured(project_root) is True

            status = get_config_status(project_root)
            assert status["configured"] is True
            assert status["user_name"] == "Integration Test User"
            assert status["target_titles_count"] == 2
            assert status["keywords_count"] == 3
            assert status["slack_configured"] is True

    def test_onboarding_with_minimal_config(self):
        """Test onboarding with only required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Minimal builder config
            builder = ProfileBuilder()
            builder.set_name("Minimal User")
            builder.set_target_titles(primary=["Engineer"])
            builder.set_keywords(primary=["python"])

            # Write files
            writer = ConfigWriter(project_root)
            writer.write_profile(builder.build(), backup=False)
            writer.write_env({
                "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T123/B456/abc",
            }, backup=False)

            # Verify
            assert is_configured(project_root) is True

    def test_profile_yaml_loadable_by_keyword_matcher(self):
        """Test that generated profile.yaml can be loaded by KeywordMatcher."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            builder = ProfileBuilder()
            builder.set_name("Matcher Test User")
            builder.set_target_titles(primary=["AI Product Manager"])
            builder.set_keywords(primary=["AI", "ML", "machine learning"])
            builder.set_salary_range(150000, 250000)
            builder.set_target_companies(tier1=["OpenAI", "Anthropic"])

            writer = ConfigWriter(project_root)
            profile_path = writer.write_profile(builder.build(), backup=False)

            # Try to load with KeywordMatcher
            from src.matching.keyword_matcher import KeywordMatcher

            matcher = KeywordMatcher(str(profile_path))

            # Verify matcher loaded the profile correctly
            assert len(matcher.primary_keywords) == 3
            assert "AI" in matcher.primary_keywords
            assert matcher.min_salary == 150000
            assert matcher.max_salary == 250000
