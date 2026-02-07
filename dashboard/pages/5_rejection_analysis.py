"""Rejection Analysis page - Identify resume gaps."""
import sys
from pathlib import Path

# Add project root to path (required for Streamlit)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from sqlalchemy import select

from dashboard.common import get_session
from src.persistence.models import Application, Job
from src.analytics.rejection_analysis import RejectionAnalyzer

st.set_page_config(
    page_title="Rejection Analysis | Job Radar",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 Rejection Analysis")
st.markdown("Analyze rejected applications to identify resume gaps and improvement opportunities.")

# Tabs
tab1, tab2 = st.tabs(["Analysis", "Add Job Descriptions"])

@st.cache_data(ttl=300)
def _cached_analysis():
    """Cache rejection analysis for 5 minutes to avoid repeated expensive queries."""
    with get_session() as session:
        analyzer = RejectionAnalyzer(session)
        return analyzer.analyze()


with tab1:
    insights = _cached_analysis()
    with get_session() as session:
        analyzer = RejectionAnalyzer(session)

        # Summary metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Total Rejected",
                insights.total_rejected,
                help="Total applications marked as rejected",
            )

        with col2:
            st.metric(
                "With Descriptions",
                insights.analyzed_with_descriptions,
                help="Rejected applications with job descriptions for analysis",
            )

        with col3:
            coverage = (
                insights.analyzed_with_descriptions / insights.total_rejected * 100
                if insights.total_rejected > 0
                else 0
            )
            st.metric(
                "Analysis Coverage",
                f"{coverage:.0f}%",
                help="% of rejections with job descriptions",
            )

        st.markdown("---")

        if insights.analyzed_with_descriptions == 0:
            st.warning(
                "No job descriptions found for rejected applications. "
                "Add job descriptions in the 'Add Job Descriptions' tab to enable analysis."
            )
        else:
            # Recommendations
            st.subheader("📋 Recommendations")
            for rec in insights.recommendations:
                st.info(rec)

            st.markdown("---")

            # Missing keywords
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("🚨 Missing Keywords")
                st.markdown("Keywords found in job descriptions but not in your profile:")

                if insights.top_missing_keywords:
                    for gap in insights.top_missing_keywords:
                        with st.expander(f"**{gap.keyword}** - found in {gap.frequency} jobs"):
                            st.write(f"Companies: {', '.join(gap.example_companies)}")
                else:
                    st.success("No significant keyword gaps found!")

            with col2:
                st.subheader("📊 Most Requested Skills")
                st.markdown("Top skills mentioned across rejected job descriptions:")

                if insights.top_required_skills:
                    for skill, count in insights.top_required_skills:
                        pct = count / insights.analyzed_with_descriptions * 100
                        st.write(f"• **{skill}** - {count} jobs ({pct:.0f}%)")
                else:
                    st.info("Add more job descriptions to see skill patterns.")

            # Common requirements
            if insights.common_requirements:
                st.markdown("---")
                st.subheader("📝 Common Requirement Phrases")
                st.markdown("Frequently mentioned requirements across rejected job descriptions:")
                for req in insights.common_requirements:
                    st.write(f"• {req}")

with tab2:
    st.subheader("Add Job Descriptions to Rejected Applications")
    st.markdown(
        "Adding job descriptions helps analyze why applications were rejected. "
        "Paste the job description from the original posting."
    )

    with get_session() as session:
        # Get rejected applications without descriptions
        stmt = select(Application).where(
            Application.status == "rejected",
        ).order_by(Application.company)
        rejected_apps = session.execute(stmt).scalars().all()

        # Filter to those without descriptions
        apps_needing_desc = []
        apps_with_desc = []

        for app in rejected_apps:
            has_desc = False
            if app.job_description:
                has_desc = True
            elif app.job_id:
                job = session.get(Job, app.job_id)
                if job and job.description:
                    has_desc = True

            if has_desc:
                apps_with_desc.append(app)
            else:
                apps_needing_desc.append(app)

        st.markdown(f"**{len(apps_needing_desc)}** rejected applications need job descriptions")
        st.markdown(f"**{len(apps_with_desc)}** already have descriptions")

        st.markdown("---")

        if apps_needing_desc:
            # Select application to add description
            app_options = {f"{app.company} - {app.position}": app.id for app in apps_needing_desc}
            selected = st.selectbox(
                "Select application to add description:",
                options=list(app_options.keys()),
            )

            if selected:
                app_id = app_options[selected]
                app = session.get(Application, app_id)

                st.markdown(f"**Company:** {app.company}")
                st.markdown(f"**Position:** {app.position}")
                st.markdown(f"**Applied:** {app.applied_date.strftime('%Y-%m-%d') if app.applied_date else 'N/A'}")

                # Job URL input
                job_url = st.text_input(
                    "Job URL (optional)",
                    value=app.job_url or "",
                    placeholder="https://company.com/jobs/...",
                )

                # Job description input
                job_desc = st.text_area(
                    "Job Description",
                    value=app.job_description or "",
                    height=300,
                    placeholder="Paste the full job description here...",
                )

                if st.button("Save Description", type="primary"):
                    if job_desc.strip():
                        app.job_url = job_url.strip() if job_url else None
                        app.job_description = job_desc.strip()
                        session.commit()
                        st.success(f"Saved description for {app.company}!")
                        st.rerun()
                    else:
                        st.error("Please enter a job description.")
        else:
            st.success("All rejected applications have job descriptions!")

        # Show applications with descriptions
        if apps_with_desc:
            st.markdown("---")
            st.subheader("Applications with Descriptions")

            for app in apps_with_desc:
                with st.expander(f"{app.company} - {app.position}"):
                    # Get description
                    desc = app.job_description
                    if not desc and app.job_id:
                        job = session.get(Job, app.job_id)
                        if job:
                            desc = job.description
                            st.caption("(Description from linked job)")

                    if desc:
                        st.text_area(
                            "Description",
                            value=desc[:1000] + "..." if len(desc) > 1000 else desc,
                            height=150,
                            disabled=True,
                            key=f"desc_{app.id}",
                        )

                    # Show keyword comparison
                    comparison = analyzer.get_keyword_comparison(app.id)
                    if comparison:
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Match: {comparison['match_percentage']:.0f}%**")
                            if comparison['matched_keywords']:
                                st.markdown("✅ Matched: " + ", ".join(comparison['matched_keywords'][:5]))
                        with col2:
                            if comparison['missing_keywords']:
                                st.markdown("❌ Missing: " + ", ".join(comparison['missing_keywords'][:5]))
