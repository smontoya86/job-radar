"""Settings page - Edit job search profile configuration."""
import sys
from pathlib import Path

# Add project root to path (required for Streamlit)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import yaml

from src.onboarding import ConfigWriter
from src.onboarding.validators import (
    TargetTitles,
    RequiredKeywords,
    Compensation,
    Location,
    TargetCompanies,
)

st.set_page_config(page_title="Settings | Job Radar", page_icon="gear", layout="wide")

PROFILE_PATH = _project_root / "config" / "profile.yaml"


def _load_profile() -> dict:
    """Load current profile.yaml as a dict."""
    if not PROFILE_PATH.exists():
        return {}
    with open(PROFILE_PATH) as f:
        return yaml.safe_load(f) or {}


def _save_profile(profile_dict: dict, success_key: str):
    """Save profile dict to disk and set success flag."""
    writer = ConfigWriter(project_root=_project_root)
    writer.write_profile(profile_dict, backup=True)
    st.session_state[success_key] = True
    st.rerun()


def _show_saved_banner(key: str, label: str):
    """Show success banner if the given key was just saved."""
    if st.session_state.pop(key, False):
        st.success(f"{label} saved! Changes will take effect on the next scan cycle.")


def _render_titles_tab(profile_dict: dict):
    """Render the Titles / Roles editing tab."""
    _show_saved_banner("titles_saved", "Titles")

    titles = profile_dict.get("target_titles", {})

    st.markdown("Jobs with matching titles score higher in search results. "
                "**Primary titles** are your main targets. "
                "**Secondary titles** are nice-to-have alternatives.")

    primary_text = st.text_area(
        "Primary Job Titles (one per line)",
        value="\n".join(titles.get("primary", [])),
        height=200,
        help="These are your main target titles. At least one is required.",
        placeholder="Software Engineer\nSenior Software Engineer\nStaff Engineer",
    )
    primary_list = [t.strip() for t in primary_text.split("\n") if t.strip()]

    secondary_text = st.text_area(
        "Secondary Job Titles (optional, one per line)",
        value="\n".join(titles.get("secondary", [])),
        height=150,
        help="Alternative titles you'd also consider",
        placeholder="Backend Engineer\nPlatform Engineer",
    )
    secondary_list = [t.strip() for t in secondary_text.split("\n") if t.strip()]

    st.caption(f"Primary: {len(primary_list)} titles | Secondary: {len(secondary_list)} titles")

    if st.button("Save Titles", type="primary"):
        try:
            TargetTitles(primary=primary_list, secondary=secondary_list)
        except Exception as e:
            st.error(f"Validation error: {e}")
            return
        profile_dict["target_titles"] = {"primary": primary_list, "secondary": secondary_list}
        try:
            _save_profile(profile_dict, "titles_saved")
        except Exception as e:
            st.error(f"Failed to save: {e}")


def _render_keywords_tab(profile_dict: dict):
    """Render the Keywords editing tab."""
    _show_saved_banner("keywords_saved", "Keywords")

    keywords = profile_dict.get("required_keywords", {})
    negative = profile_dict.get("negative_keywords", [])

    st.markdown("**Primary keywords** must appear in job listings. "
                "**Secondary keywords** give bonus points. "
                "**Negative keywords** exclude jobs entirely.")

    col1, col2 = st.columns(2)
    with col1:
        primary_text = st.text_area(
            "Primary Keywords (one per line)",
            value="\n".join(keywords.get("primary", [])),
            height=200,
            help="At least one primary keyword is required.",
            placeholder="python\nbackend\nAPI",
        )
    with col2:
        secondary_text = st.text_area(
            "Secondary Keywords (optional, one per line)",
            value="\n".join(keywords.get("secondary", [])),
            height=200,
            help="Bonus points for these keywords",
            placeholder="kubernetes\nDocker\nCI/CD",
        )

    primary_list = [k.strip() for k in primary_text.split("\n") if k.strip()]
    secondary_list = [k.strip() for k in secondary_text.split("\n") if k.strip()]

    negative_text = st.text_area(
        "Negative Keywords (one per line)",
        value="\n".join(negative),
        height=120,
        help="Jobs containing these words will be excluded",
        placeholder="junior\nintern\ncontract",
    )
    negative_list = [k.strip() for k in negative_text.split("\n") if k.strip()]

    st.caption(f"Primary: {len(primary_list)} | Secondary: {len(secondary_list)} | Negative: {len(negative_list)}")

    if st.button("Save Keywords", type="primary"):
        try:
            RequiredKeywords(primary=primary_list, secondary=secondary_list)
        except Exception as e:
            st.error(f"Validation error: {e}")
            return
        profile_dict["required_keywords"] = {"primary": primary_list, "secondary": secondary_list}
        profile_dict["negative_keywords"] = negative_list
        try:
            _save_profile(profile_dict, "keywords_saved")
        except Exception as e:
            st.error(f"Failed to save: {e}")


def _render_salary_tab(profile_dict: dict):
    """Render the Salary & Location editing tab."""
    _show_saved_banner("salary_saved", "Salary & Location")

    comp = profile_dict.get("compensation", {})
    loc = profile_dict.get("location", {})

    st.subheader("Compensation")
    col1, col2, col3 = st.columns(3)
    with col1:
        min_salary = st.number_input(
            "Minimum Salary",
            min_value=0, max_value=1_000_000, step=5000,
            value=comp.get("min_salary", 100000),
        )
    with col2:
        max_salary = st.number_input(
            "Maximum Salary",
            min_value=0, max_value=1_000_000, step=5000,
            value=comp.get("max_salary", 200000),
        )
    with col3:
        currency = st.text_input("Currency", value=comp.get("currency", "USD"))

    flexible = st.checkbox("Flexible (open to great opportunities outside range)",
                           value=comp.get("flexible", True))

    st.divider()
    st.subheader("Location")

    remote_only = st.checkbox("Remote only", value=loc.get("remote_only", False))

    col1, col2 = st.columns(2)
    with col1:
        preferred_text = st.text_area(
            "Preferred Locations (one per line)",
            value="\n".join(loc.get("preferred", ["Remote"])),
            height=150,
            placeholder="Remote\nSan Francisco\nNew York",
        )
    with col2:
        excluded_text = st.text_area(
            "Excluded Locations (one per line)",
            value="\n".join(loc.get("excluded", [])),
            height=150,
            placeholder="Countries or cities to exclude",
        )

    preferred_list = [l.strip() for l in preferred_text.split("\n") if l.strip()]
    excluded_list = [l.strip() for l in excluded_text.split("\n") if l.strip()]

    if st.button("Save Salary & Location", type="primary"):
        try:
            Compensation(min_salary=min_salary, max_salary=max_salary,
                         flexible=flexible, currency=currency)
            Location(remote_only=remote_only, preferred=preferred_list, excluded=excluded_list)
        except Exception as e:
            st.error(f"Validation error: {e}")
            return
        profile_dict["compensation"] = {
            "min_salary": min_salary,
            "max_salary": max_salary,
            "flexible": flexible,
            "currency": currency,
        }
        profile_dict["location"] = {
            "remote_only": remote_only,
            "preferred": preferred_list,
            "excluded": excluded_list,
        }
        try:
            _save_profile(profile_dict, "salary_saved")
        except Exception as e:
            st.error(f"Failed to save: {e}")


def _render_companies_tab(profile_dict: dict):
    """Render the Companies editing tab."""
    _show_saved_banner("companies_saved", "Companies")

    companies = profile_dict.get("target_companies", {})

    st.markdown("Organize target companies by tier. "
                "**Tier 1** = dream companies, **Tier 2** = great companies, "
                "**Tier 3** = good companies. Higher tiers score higher in matching.")

    col1, col2, col3 = st.columns(3)
    with col1:
        tier1_text = st.text_area(
            "Tier 1 - Dream (one per line)",
            value="\n".join(companies.get("tier1", [])),
            height=250,
            placeholder="Google\nApple\nMeta",
        )
    with col2:
        tier2_text = st.text_area(
            "Tier 2 - Great (one per line)",
            value="\n".join(companies.get("tier2", [])),
            height=250,
            placeholder="Stripe\nAirbnb\nNotion",
        )
    with col3:
        tier3_text = st.text_area(
            "Tier 3 - Good (one per line)",
            value="\n".join(companies.get("tier3", [])),
            height=250,
            placeholder="Spotify\nReddit\nDiscord",
        )

    tier1_list = [c.strip() for c in tier1_text.split("\n") if c.strip()]
    tier2_list = [c.strip() for c in tier2_text.split("\n") if c.strip()]
    tier3_list = [c.strip() for c in tier3_text.split("\n") if c.strip()]

    st.caption(f"Tier 1: {len(tier1_list)} | Tier 2: {len(tier2_list)} | Tier 3: {len(tier3_list)}")

    if st.button("Save Companies", type="primary"):
        try:
            TargetCompanies(tier1=tier1_list, tier2=tier2_list, tier3=tier3_list)
        except Exception as e:
            st.error(f"Validation error: {e}")
            return
        profile_dict["target_companies"] = {
            "tier1": tier1_list,
            "tier2": tier2_list,
            "tier3": tier3_list,
        }
        try:
            _save_profile(profile_dict, "companies_saved")
        except Exception as e:
            st.error(f"Failed to save: {e}")


def main():
    st.title("Settings")

    if not PROFILE_PATH.exists():
        st.warning("No profile configured yet. Please complete the Setup Wizard first.")
        return

    profile_dict = _load_profile()

    profile = profile_dict.get("profile", {})
    name = profile.get("name", "")
    if name:
        st.caption(f"Profile: {name}")

    tab_titles, tab_keywords, tab_salary, tab_companies = st.tabs([
        "Titles / Roles",
        "Keywords",
        "Salary & Location",
        "Companies",
    ])

    with tab_titles:
        _render_titles_tab(profile_dict)

    with tab_keywords:
        _render_keywords_tab(profile_dict)

    with tab_salary:
        _render_salary_tab(profile_dict)

    with tab_companies:
        _render_companies_tab(profile_dict)


main()
