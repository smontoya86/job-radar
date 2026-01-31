"""Main Streamlit dashboard application."""
import sys
from pathlib import Path

# Add project root to path (required for Streamlit to find dashboard module)
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from dashboard.common import get_session, settings


def main():
    """Main entry point for the dashboard."""
    # Database initialized by dashboard.common on import

    # Page config
    st.set_page_config(
        page_title="Job Radar",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS
    st.markdown(
        """
        <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 1rem;
        }
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 1rem;
            border-radius: 0.5rem;
            color: white;
        }
        .status-applied { color: #3498db; }
        .status-phone_screen { color: #9b59b6; }
        .status-interviewing { color: #e67e22; }
        .status-offer { color: #27ae60; }
        .status-accepted { color: #2ecc71; }
        .status-rejected { color: #e74c3c; }
        .status-withdrawn { color: #95a5a6; }
        .status-ghosted { color: #7f8c8d; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/radar.png", width=80)
        st.title("Job Radar")
        st.markdown("---")

        # Quick stats
        with get_session() as session:
            from src.analytics.funnel import FunnelAnalytics

            funnel = FunnelAnalytics(session)
            active_count = funnel.get_active_pipeline_count()
            interview_rate = funnel.get_interview_rate()

        st.metric("Active Applications", active_count)
        st.metric("Interview Rate", f"{interview_rate:.1f}%")

        st.markdown("---")
        st.markdown("### Navigation")
        st.markdown("Use the pages in the sidebar to navigate.")

        st.markdown("---")
        st.markdown("### Quick Actions")

        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

        if st.button("📧 Sync Email"):
            with st.spinner("Syncing emails..."):
                try:
                    import asyncio
                    from src.main import run_email_import
                    asyncio.run(run_email_import())
                    st.success("Email sync complete!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Sync failed: {e}")

        if st.button("📊 Run Job Scan"):
            with st.spinner("Running job scan..."):
                try:
                    import asyncio
                    from src.main import run_job_scan
                    asyncio.run(run_job_scan())
                    st.success("Job scan complete!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Scan failed: {e}")

    # Main content - Home page
    st.markdown('<p class="main-header">🎯 Job Radar Dashboard</p>', unsafe_allow_html=True)

    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)

    with get_session() as session:
        from sqlalchemy import func, select

        from src.persistence.models import Application, Job

        # Total jobs found
        stmt = select(func.count(Job.id))
        total_jobs = session.execute(stmt).scalar() or 0

        # Total applications
        stmt = select(func.count(Application.id))
        total_apps = session.execute(stmt).scalar() or 0

        # Interviews scheduled
        stmt = select(func.count(Application.id)).where(
            Application.status.in_(["phone_screen", "interviewing"])
        )
        interviews = session.execute(stmt).scalar() or 0

        # Offers
        stmt = select(func.count(Application.id)).where(
            Application.status.in_(["offer", "accepted"])
        )
        offers = session.execute(stmt).scalar() or 0

    with col1:
        st.metric("Jobs Found", total_jobs, help="Total jobs discovered by radar")

    with col2:
        st.metric("Applications", total_apps, help="Total applications submitted")

    with col3:
        st.metric("Interviews", interviews, help="Active interviews")

    with col4:
        st.metric("Offers", offers, help="Offers received")

    st.markdown("---")

    # Recent activity
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📋 Recent Applications")

        with get_session() as session:
            from src.tracking.application_service import ApplicationService

            app_service = ApplicationService(session)
            recent_apps = app_service.get_all_applications(limit=5)

            if recent_apps:
                for app in recent_apps:
                    status_class = f"status-{app.status}"
                    st.markdown(
                        f"""
                        **{app.company}** - {app.position}
                        <span class="{status_class}">{app.status.title()}</span>
                        | Applied: {app.applied_date.strftime('%m/%d/%Y') if app.applied_date else 'N/A'}
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown("---")
            else:
                st.info("No applications yet. Start applying to jobs!")

    with col2:
        st.subheader("🎯 Top Job Matches")

        with get_session() as session:
            # Get recent high-scoring jobs
            stmt = (
                select(Job)
                .where(Job.status == "new", Job.match_score >= 50)
                .order_by(Job.match_score.desc())
                .limit(5)
            )
            result = session.execute(stmt)
            top_jobs = list(result.scalars().all())

            if top_jobs:
                for job in top_jobs:
                    score_emoji = "🔥" if job.match_score >= 80 else "✨" if job.match_score >= 60 else "📋"
                    remote_badge = "🏠" if job.remote else ""

                    st.markdown(
                        f"""
                        {score_emoji} **[{job.title}]({job.url})**
                        {job.company} {remote_badge} | Score: {job.match_score:.0f}%
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown("---")
            else:
                st.info("No new job matches. Run a job scan to find opportunities!")

    # Application funnel preview
    st.markdown("---")
    st.subheader("📊 Application Funnel")

    with get_session() as session:
        from src.analytics.funnel import FunnelAnalytics

        funnel = FunnelAnalytics(session)
        funnel_data = funnel.get_funnel()

        if funnel_data.total_applications > 0:
            import plotly.graph_objects as go

            fig = go.Figure(
                go.Funnel(
                    y=[stage.name for stage in funnel_data.stages],
                    x=[stage.count for stage in funnel_data.stages],
                    textposition="inside",
                    textinfo="value+percent initial",
                    marker=dict(
                        color=[
                            "#3498db",
                            "#9b59b6",
                            "#e67e22",
                            "#f39c12",
                            "#27ae60",
                            "#2ecc71",
                            "#1abc9c",
                        ]
                    ),
                )
            )
            fig.update_layout(
                height=400,
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No application data yet. Start tracking your applications!")

    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align: center; color: #666;">
            Job Radar v1.0 | Built for your job search success 🚀
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
