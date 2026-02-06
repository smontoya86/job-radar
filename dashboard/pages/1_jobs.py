"""Jobs page - View and manage job matches."""
import sys
from pathlib import Path

# Add project root to path (required for Streamlit)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from sqlalchemy import select

from dashboard.common import get_session
from src.persistence.models import Job, Application
from src.tracking.application_service import ApplicationService

st.set_page_config(page_title="Jobs | Job Radar", page_icon="🎯", layout="wide")

st.title("🎯 Job Matches")
st.markdown("Browse and manage job matches from the radar.")

# Filters
st.sidebar.header("Filters")

min_score = st.sidebar.slider("Minimum Score", 0, 100, 50)

status_filter = st.sidebar.multiselect(
    "Status",
    ["new", "saved", "applied", "dismissed"],
    default=["new", "saved"],
)

remote_only = st.sidebar.checkbox("Remote Only", value=False)
hide_applied = st.sidebar.checkbox("Hide Already Applied", value=True)

source_filter = st.sidebar.multiselect(
    "Source",
    ["serpapi", "jsearch", "ashby", "workday", "smartrecruiters", "search_discovery",
     "email_alerts", "greenhouse", "lever", "remoteok", "hn_whoishiring", "adzuna"],
    default=[],
)

# Sort options
sort_by = st.sidebar.selectbox(
    "Sort By",
    ["Match Score", "Posted Date", "Company", "Discovered Date"],
)

sort_order = st.sidebar.radio("Order", ["Descending", "Ascending"])

# Main content
with get_session() as session:
    # Build query
    stmt = select(Job)

    # Apply filters
    if min_score > 0:
        stmt = stmt.where(Job.match_score >= min_score)

    if status_filter:
        stmt = stmt.where(Job.status.in_(status_filter))

    if remote_only:
        stmt = stmt.where(Job.remote == True)

    if source_filter:
        stmt = stmt.where(Job.source.in_(source_filter))

    # Apply sorting
    sort_column = {
        "Match Score": Job.match_score,
        "Posted Date": Job.posted_date,
        "Company": Job.company,
        "Discovered Date": Job.discovered_at,
    }.get(sort_by, Job.match_score)

    if sort_order == "Descending":
        stmt = stmt.order_by(sort_column.desc())
    else:
        stmt = stmt.order_by(sort_column.asc())

    stmt = stmt.limit(100)

    result = session.execute(stmt)
    jobs = list(result.scalars().all())

    # Filter out jobs already applied for
    if hide_applied:
        # Get all applications
        applications = session.query(Application).all()

        # Build set of (company_lower, position_keywords) for matching
        applied_jobs = set()
        for app in applications:
            company_lower = app.company.lower().strip()
            # Also store key words from position to match similar titles
            position_words = set(app.position.lower().split())
            applied_jobs.add((company_lower, frozenset(position_words)))

        def is_already_applied(job):
            """Check if this job matches an existing application."""
            job_company = job.company.lower().strip()
            job_title_words = set(job.title.lower().split())

            for app_company, app_position_words in applied_jobs:
                # Check if company matches (fuzzy - one contains the other)
                company_match = (
                    app_company in job_company or
                    job_company in app_company or
                    app_company.replace(' ', '') == job_company.replace(' ', '')
                )

                if company_match:
                    # Check if position has significant overlap (at least 2 key words match)
                    # Filter out common words
                    common_words = {'the', 'a', 'an', 'and', 'or', 'of', 'for', 'at', 'in', '-', '–', '|'}
                    job_keywords = job_title_words - common_words
                    app_keywords = app_position_words - common_words

                    overlap = len(job_keywords & app_keywords)
                    if overlap >= 2 or (overlap >= 1 and len(app_keywords) <= 3):
                        return True
            return False

        original_count = len(jobs)
        jobs = [j for j in jobs if not is_already_applied(j)]
        filtered_count = original_count - len(jobs)
        if filtered_count > 0:
            st.sidebar.info(f"Hiding {filtered_count} jobs you've already applied for")

    # Display stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Jobs Found", len(jobs))
    with col2:
        avg_score = sum(j.match_score or 0 for j in jobs) / len(jobs) if jobs else 0
        st.metric("Avg Score", f"{avg_score:.0f}%")
    with col3:
        remote_count = sum(1 for j in jobs if j.remote)
        st.metric("Remote", remote_count)

    st.markdown("---")

    if not jobs:
        st.info("No jobs match your filters. Try adjusting the criteria or run a job scan.")
    else:
        # Display jobs
        for job in jobs:
            with st.container():
                col1, col2 = st.columns([4, 1])

                with col1:
                    # Score emoji
                    score = job.match_score or 0
                    if score >= 80:
                        score_emoji = "🔥"
                    elif score >= 60:
                        score_emoji = "✨"
                    else:
                        score_emoji = "📋"

                    remote_badge = "🏠" if job.remote else ""

                    st.markdown(
                        f"""
                        ### {score_emoji} [{job.title}]({job.url})
                        **{job.company}** {remote_badge} | {job.location or 'Location not specified'}
                        """
                    )

                    # Details row
                    details = []
                    if job.salary_min and job.salary_max:
                        details.append(f"💰 ${job.salary_min:,}-${job.salary_max:,}")
                    elif job.salary_min:
                        details.append(f"💰 ${job.salary_min:,}+")

                    details.append(f"📍 {job.source}")
                    details.append(f"⭐ Score: {score:.0f}%")

                    if job.posted_date:
                        details.append(f"📅 Posted: {job.posted_date.strftime('%m/%d')}")

                    st.markdown(" | ".join(details))

                    # Keywords
                    if job.matched_keywords:
                        keywords = job.matched_keywords[:6]
                        st.markdown(f"**Keywords:** {', '.join(keywords)}")

                with col2:
                    # Action buttons
                    st.markdown("<br>", unsafe_allow_html=True)

                    if st.button("🚀 Apply", key=f"apply_{job.id}"):
                        # Mark as applied and create application
                        app_service = ApplicationService(session)
                        app_service.create_application(
                            company=job.company,
                            position=job.title,
                            source=job.source,
                            job_id=job.id,
                        )
                        job.status = "applied"
                        session.commit()
                        st.success(f"Applied to {job.company}!")
                        st.rerun()

                    if job.status == "new":
                        if st.button("⭐ Save", key=f"save_{job.id}"):
                            job.status = "saved"
                            session.commit()
                            st.success("Saved!")
                            st.rerun()

                    if st.button("👋 Dismiss", key=f"dismiss_{job.id}"):
                        job.status = "dismissed"
                        session.commit()
                        st.rerun()

                st.markdown("---")

# Bulk actions
st.sidebar.markdown("---")
st.sidebar.header("Bulk Actions")

if st.sidebar.button("Dismiss All Low Score (<40)"):
    with get_session() as session:
        stmt = select(Job).where(Job.match_score < 40, Job.status == "new")
        result = session.execute(stmt)
        low_score_jobs = list(result.scalars().all())

        for job in low_score_jobs:
            job.status = "dismissed"

        session.commit()
        st.sidebar.success(f"Dismissed {len(low_score_jobs)} jobs")
        st.rerun()
