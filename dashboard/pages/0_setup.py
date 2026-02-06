"""Setup wizard page - Configure Job Radar for first use."""
import sys
from pathlib import Path

# Add project root to path (required for Streamlit)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import requests

from src.onboarding import ProfileBuilder, ConfigWriter, get_missing_config
from src.onboarding.config_checker import get_config_status

st.set_page_config(page_title="Setup | Job Radar", page_icon="🚀", layout="wide")

# Constants
TOTAL_STEPS = 9
DEFAULT_NEGATIVE_KEYWORDS = [
    "junior", "associate", "entry level", "entry-level",
    "intern", "internship", "contract", "contractor", "C2C"
]
DEFAULT_SOURCES = [
    "serpapi", "jsearch", "ashby", "workday", "smartrecruiters",
    "search_discovery", "greenhouse", "lever", "remoteok", "hn_whoishiring"
]


def init_session_state():
    """Initialize session state for wizard."""
    if "setup_step" not in st.session_state:
        st.session_state.setup_step = 1

    if "builder" not in st.session_state:
        st.session_state.builder = ProfileBuilder()

    if "env_config" not in st.session_state:
        st.session_state.env_config = {
            "SLACK_WEBHOOK_URL": "",
            "DATABASE_URL": "sqlite:///data/job_radar.db",
            "DASHBOARD_PORT": "8501",
            "JOB_CHECK_INTERVAL_MINUTES": "30",
            "EMAIL_CHECK_INTERVAL_MINUTES": "15",
        }

    if "setup_complete" not in st.session_state:
        st.session_state.setup_complete = False


def next_step():
    """Move to next wizard step."""
    st.session_state.setup_step = min(st.session_state.setup_step + 1, TOTAL_STEPS)


def prev_step():
    """Move to previous wizard step."""
    st.session_state.setup_step = max(st.session_state.setup_step - 1, 1)


def go_to_step(step: int):
    """Go to specific step."""
    st.session_state.setup_step = max(1, min(step, TOTAL_STEPS))


def test_slack_webhook(url: str) -> tuple[bool, str]:
    """Test Slack webhook URL.

    Returns:
        Tuple of (success, message)
    """
    if not url or not url.startswith("https://hooks.slack.com/"):
        return False, "Invalid webhook URL format"

    try:
        response = requests.post(
            url,
            json={"text": "Job Radar setup test message - your webhook is working!"},
            timeout=10,
        )
        if response.status_code == 200:
            return True, "Webhook test successful!"
        else:
            return False, f"Webhook returned status {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {e}"


def render_progress():
    """Render progress bar and step indicators."""
    progress = st.session_state.setup_step / TOTAL_STEPS
    st.progress(progress)

    steps = [
        "Welcome", "Basic Info", "Job Titles", "Keywords",
        "Salary", "Location", "Companies", "Notifications", "Review"
    ]

    # Show step pills
    cols = st.columns(TOTAL_STEPS)
    for i, (col, step_name) in enumerate(zip(cols, steps), 1):
        with col:
            if i < st.session_state.setup_step:
                st.markdown(f"✅ ~~{i}~~")
            elif i == st.session_state.setup_step:
                st.markdown(f"**{i}**")
            else:
                st.markdown(f"{i}")

    st.caption(f"Step {st.session_state.setup_step} of {TOTAL_STEPS}: {steps[st.session_state.setup_step - 1]}")
    st.divider()


def render_step_1():
    """Welcome step."""
    st.header("Welcome to Job Radar!")

    st.markdown("""
    This setup wizard will help you configure Job Radar for your job search.

    **What you'll configure:**
    - Your target job titles and seniority level
    - Keywords to match in job descriptions
    - Salary and location preferences
    - Target companies (optional)
    - Slack notifications

    **What you'll need:**
    - A Slack workspace with permission to add apps (for notifications)
    - About 5 minutes to complete setup

    Your configuration will be saved to `config/profile.yaml` and `.env` files.
    """)

    st.info("You can always come back and modify your settings later.")

    if st.button("Get Started →", type="primary", use_container_width=True):
        next_step()
        st.rerun()


def render_step_2():
    """Basic info step."""
    st.header("Basic Information")

    builder = st.session_state.builder

    builder.name = st.text_input(
        "Your Name",
        value=builder.name,
        help="Used for personalization in notifications"
    )

    builder.experience_years = st.number_input(
        "Years of Experience",
        min_value=0,
        max_value=50,
        value=builder.experience_years,
        help="Helps filter out junior/senior level mismatches"
    )

    builder.remote_preference = st.checkbox(
        "I prefer remote work",
        value=builder.remote_preference,
        help="Remote jobs will be scored higher"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Next →", type="primary", disabled=not builder.name):
            next_step()
            st.rerun()

    if not builder.name:
        st.warning("Please enter your name to continue")


def render_step_3():
    """Target titles step."""
    st.header("Target Job Titles")

    st.markdown("""
    Enter the job titles you're looking for. Jobs with matching titles will score higher.

    **Primary titles** are your main targets. **Secondary titles** are nice-to-have alternatives.
    """)

    builder = st.session_state.builder

    primary_text = st.text_area(
        "Primary Job Titles (one per line)",
        value="\n".join(builder.target_titles_primary),
        height=150,
        help="These are your main target titles",
        placeholder="Software Engineer\nSenior Software Engineer\nStaff Engineer"
    )
    builder.target_titles_primary = [t.strip() for t in primary_text.split("\n") if t.strip()]

    secondary_text = st.text_area(
        "Secondary Job Titles (optional, one per line)",
        value="\n".join(builder.target_titles_secondary),
        height=100,
        help="Alternative titles you'd also consider",
        placeholder="Backend Engineer\nPlatform Engineer"
    )
    builder.target_titles_secondary = [t.strip() for t in secondary_text.split("\n") if t.strip()]

    st.caption(f"Primary: {len(builder.target_titles_primary)} titles | Secondary: {len(builder.target_titles_secondary)} titles")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Next →", type="primary", disabled=len(builder.target_titles_primary) == 0):
            next_step()
            st.rerun()

    if len(builder.target_titles_primary) == 0:
        st.warning("Please enter at least one primary job title")


def render_step_4():
    """Keywords step."""
    st.header("Search Keywords")

    st.markdown("""
    Enter keywords that should appear in job descriptions. Jobs mentioning these keywords will score higher.

    **Primary keywords** are required - jobs must mention at least one.
    **Secondary keywords** provide bonus points.
    **Negative keywords** will exclude jobs that mention them.
    """)

    builder = st.session_state.builder

    primary_text = st.text_area(
        "Primary Keywords (one per line)",
        value="\n".join(builder.keywords_primary),
        height=150,
        help="Jobs must mention at least one of these",
        placeholder="python\nbackend\nAPI\ndistributed systems"
    )
    builder.keywords_primary = [k.strip() for k in primary_text.split("\n") if k.strip()]

    col1, col2 = st.columns(2)

    with col1:
        secondary_text = st.text_area(
            "Secondary Keywords (optional)",
            value="\n".join(builder.keywords_secondary),
            height=120,
            help="Bonus keywords that add points",
            placeholder="kubernetes\nAWS\nmicroservices"
        )
        builder.keywords_secondary = [k.strip() for k in secondary_text.split("\n") if k.strip()]

    with col2:
        negative_text = st.text_area(
            "Negative Keywords (exclude jobs with these)",
            value="\n".join(builder.negative_keywords),
            height=120,
            help="Jobs containing these words will be excluded",
        )
        builder.negative_keywords = [k.strip() for k in negative_text.split("\n") if k.strip()]

    st.caption(f"Primary: {len(builder.keywords_primary)} | Secondary: {len(builder.keywords_secondary)} | Negative: {len(builder.negative_keywords)}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Next →", type="primary", disabled=len(builder.keywords_primary) == 0):
            next_step()
            st.rerun()

    if len(builder.keywords_primary) == 0:
        st.warning("Please enter at least one primary keyword")


def render_step_5():
    """Salary step."""
    st.header("Compensation Preferences")

    builder = st.session_state.builder

    col1, col2 = st.columns(2)

    with col1:
        builder.salary_min = st.number_input(
            "Minimum Salary (USD)",
            min_value=0,
            max_value=1000000,
            value=builder.salary_min,
            step=5000,
            help="Jobs below this won't be penalized but won't get bonus points"
        )

    with col2:
        builder.salary_max = st.number_input(
            "Target/Maximum Salary (USD)",
            min_value=0,
            max_value=1000000,
            value=builder.salary_max,
            step=5000,
            help="Your target salary range"
        )

    builder.salary_flexible = st.checkbox(
        "I'm flexible on salary for the right opportunity",
        value=builder.salary_flexible,
        help="If checked, salary won't be a hard filter"
    )

    if builder.salary_min > builder.salary_max:
        st.error("Minimum salary cannot be greater than maximum salary")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Next →", type="primary", disabled=builder.salary_min > builder.salary_max):
            next_step()
            st.rerun()


def render_step_6():
    """Location step."""
    st.header("Location Preferences")

    builder = st.session_state.builder

    builder.remote_only = st.checkbox(
        "Only show remote jobs",
        value=builder.remote_only,
        help="If checked, only remote positions will be shown"
    )

    preferred_text = st.text_area(
        "Preferred Locations (one per line)",
        value="\n".join(builder.locations_preferred),
        height=120,
        help="Locations you'd consider working in",
        placeholder="Remote\nSan Francisco\nNew York\nSeattle"
    )
    builder.locations_preferred = [l.strip() for l in preferred_text.split("\n") if l.strip()]

    excluded_text = st.text_area(
        "Excluded Locations (optional, one per line)",
        value="\n".join(builder.locations_excluded),
        height=80,
        help="Locations to exclude from results",
        placeholder="India\nPhilippines"
    )
    builder.locations_excluded = [l.strip() for l in excluded_text.split("\n") if l.strip()]

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Next →", type="primary"):
            next_step()
            st.rerun()


def render_step_7():
    """Target companies step."""
    st.header("Target Companies (Optional)")

    st.markdown("""
    Organize your target companies into tiers. Jobs from higher-tier companies will score higher.

    This is optional - you can leave these empty and add companies later.
    """)

    builder = st.session_state.builder

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Tier 1: Dream Companies")
        tier1_text = st.text_area(
            "Dream companies",
            value="\n".join(builder.companies_tier1),
            height=150,
            label_visibility="collapsed",
            placeholder="Google\nMeta\nApple\nOpenAI"
        )
        builder.companies_tier1 = [c.strip() for c in tier1_text.split("\n") if c.strip()]

    with col2:
        st.subheader("Tier 2: Great Companies")
        tier2_text = st.text_area(
            "Great companies",
            value="\n".join(builder.companies_tier2),
            height=150,
            label_visibility="collapsed",
            placeholder="Stripe\nAirbnb\nFigma\nNotion"
        )
        builder.companies_tier2 = [c.strip() for c in tier2_text.split("\n") if c.strip()]

    with col3:
        st.subheader("Tier 3: Good Companies")
        tier3_text = st.text_area(
            "Good companies",
            value="\n".join(builder.companies_tier3),
            height=150,
            label_visibility="collapsed",
            placeholder="Spotify\nPinterest\nReddit"
        )
        builder.companies_tier3 = [c.strip() for c in tier3_text.split("\n") if c.strip()]

    total = len(builder.companies_tier1) + len(builder.companies_tier2) + len(builder.companies_tier3)
    st.caption(f"Total: {total} companies across all tiers")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Next →", type="primary"):
            next_step()
            st.rerun()


def render_step_8():
    """Notifications step."""
    st.header("Slack Notifications")

    st.markdown("""
    Job Radar sends notifications to Slack when new matching jobs are found.

    **To set up Slack notifications:**
    1. Go to [api.slack.com/apps](https://api.slack.com/apps)
    2. Click "Create New App" → "From scratch"
    3. Give it a name (e.g., "Job Radar") and select your workspace
    4. Go to "Incoming Webhooks" and turn it on
    5. Click "Add New Webhook to Workspace"
    6. Select a channel and authorize
    7. Copy the webhook URL and paste it below
    """)

    env = st.session_state.env_config
    builder = st.session_state.builder

    webhook_url = st.text_input(
        "Slack Webhook URL",
        value=env.get("SLACK_WEBHOOK_URL", ""),
        type="password",
        help="Starts with https://hooks.slack.com/services/...",
        placeholder="https://hooks.slack.com/services/T.../B.../..."
    )
    env["SLACK_WEBHOOK_URL"] = webhook_url

    if webhook_url:
        if st.button("Test Webhook"):
            with st.spinner("Testing webhook..."):
                success, message = test_slack_webhook(webhook_url)
            if success:
                st.success(message)
            else:
                st.error(message)

    st.divider()

    builder.slack_min_score = st.slider(
        "Minimum score for notifications",
        min_value=0,
        max_value=100,
        value=builder.slack_min_score,
        help="Only jobs scoring above this threshold will trigger notifications"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            prev_step()
            st.rerun()
    with col2:
        if st.button("Next →", type="primary"):
            next_step()
            st.rerun()

    if not webhook_url:
        st.warning("Slack webhook is required for notifications. You can add it later in the .env file.")


def render_step_9():
    """Review and save step."""
    st.header("Review & Save Configuration")

    builder = st.session_state.builder
    env = st.session_state.env_config

    # Validate configuration
    is_valid, error = builder.is_valid()

    if not is_valid:
        st.error(f"Configuration error: {error}")
        st.warning("Please go back and fix the issues before saving.")
    else:
        st.success("Configuration is valid!")

    # Show summary
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Profile Summary")
        st.markdown(f"""
        - **Name:** {builder.name}
        - **Experience:** {builder.experience_years} years
        - **Remote Preference:** {"Yes" if builder.remote_preference else "No"}
        - **Target Titles:** {len(builder.target_titles_primary)} primary, {len(builder.target_titles_secondary)} secondary
        - **Keywords:** {len(builder.keywords_primary)} primary, {len(builder.keywords_secondary)} secondary
        - **Salary Range:** ${builder.salary_min:,} - ${builder.salary_max:,}
        - **Locations:** {len(builder.locations_preferred)} preferred
        - **Target Companies:** {len(builder.companies_tier1) + len(builder.companies_tier2) + len(builder.companies_tier3)} total
        """)

    with col2:
        st.subheader("Notification Settings")
        webhook_set = bool(env.get("SLACK_WEBHOOK_URL"))
        st.markdown(f"""
        - **Slack Webhook:** {"Configured" if webhook_set else "Not set"}
        - **Min Score for Alerts:** {builder.slack_min_score}
        """)

    st.divider()

    # Preview YAML
    with st.expander("Preview profile.yaml"):
        config = builder.build()
        import yaml
        st.code(yaml.dump(config, default_flow_style=False, sort_keys=False), language="yaml")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("← Back"):
            prev_step()
            st.rerun()

    with col2:
        if st.button("Save Configuration", type="primary", disabled=not is_valid):
            try:
                writer = ConfigWriter(_project_root)

                # Write profile.yaml
                profile_path = writer.write_profile(builder.build())
                st.success(f"Saved profile to {profile_path}")

                # Write .env
                env_path = writer.write_env(env)
                st.success(f"Saved environment to {env_path}")

                st.session_state.setup_complete = True
                st.balloons()

            except Exception as e:
                st.error(f"Error saving configuration: {e}")

    if st.session_state.setup_complete:
        st.divider()
        st.success("Setup complete! You can now start using Job Radar.")

        st.markdown("""
        **Next steps:**
        1. Go to the **Jobs** page to see job matches
        2. The scanner will automatically find new jobs every 30 minutes
        3. You'll receive Slack notifications for high-scoring matches

        To run the job scanner manually:
        ```bash
        python src/main.py
        ```
        """)


def main():
    """Main setup wizard."""
    init_session_state()

    # Check if already configured
    status = get_config_status(_project_root)

    # Title
    st.title("🚀 Setup Wizard")

    if status["configured"] and not st.session_state.setup_complete:
        st.success("Job Radar is already configured!")
        st.markdown(f"**Current user:** {status.get('user_name', 'Unknown')}")

        if st.button("Reconfigure Settings"):
            st.session_state.setup_step = 1
            st.rerun()

        st.divider()
        st.markdown("Use the sidebar to navigate to other pages.")
        return

    # Show progress
    render_progress()

    # Render current step
    step_renderers = {
        1: render_step_1,
        2: render_step_2,
        3: render_step_3,
        4: render_step_4,
        5: render_step_5,
        6: render_step_6,
        7: render_step_7,
        8: render_step_8,
        9: render_step_9,
    }

    renderer = step_renderers.get(st.session_state.setup_step)
    if renderer:
        renderer()


if __name__ == "__main__":
    main()
