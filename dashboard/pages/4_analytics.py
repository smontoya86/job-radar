"""Analytics page - Insights and metrics."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Add project root to path (required for Streamlit)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import plotly.graph_objects as go

from dashboard.common import get_session
from src.analytics.funnel import FunnelAnalytics
from src.analytics.source_analysis import SourceAnalytics
from src.analytics.resume_analysis import ResumeAnalytics
from dashboard.components.charts import (
    create_funnel_chart,
    create_source_comparison_chart,
    create_trend_chart,
    create_pipeline_bar_chart,
)

st.set_page_config(page_title="Analytics | Job Radar", page_icon="📈", layout="wide")

st.title("📈 Analytics & Insights")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Source Analysis", "Resume Performance", "Trends"])

with tab1:
    st.subheader("Application Overview")

    with get_session() as session:
        funnel = FunnelAnalytics(session)
        source_analytics = SourceAnalytics(session)

        # Key metrics
        col1, col2, col3, col4, col5 = st.columns(5)

        funnel_data = funnel.get_funnel()
        interview_rate = funnel.get_interview_rate()
        rejection_rate = funnel.get_rejection_rate()
        response_rate = funnel.get_response_rate()
        avg_rejection_time = funnel.get_average_time_to_rejection()

        with col1:
            st.metric(
                "Total Applications",
                funnel_data.total_applications,
                help="All applications submitted",
            )

        with col2:
            st.metric(
                "Interview Rate",
                f"{interview_rate:.1f}%",
                help="% of applications that reached an interview stage",
            )

        with col3:
            st.metric(
                "Rejection Rate",
                f"{rejection_rate:.1f}%",
                help="% of applications that were rejected",
            )

        with col4:
            st.metric(
                "Response Rate",
                f"{response_rate:.1f}%",
                help="% that received any response (interviews + rejections)",
            )

        with col5:
            st.metric(
                "Avg Days to Rejection",
                f"{avg_rejection_time:.0f}" if avg_rejection_time else "N/A",
                help="Average time from application to rejection",
            )

        st.markdown("---")

        # Funnel chart
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Application Funnel")
            if funnel_data.total_applications > 0:
                fig = create_funnel_chart(funnel_data)
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No application data yet.")

        with col2:
            st.subheader("Conversion Rates")

            if funnel_data.total_applications > 0:
                for stage in funnel_data.stages:
                    if stage.percentage > 0:
                        st.markdown(
                            f"""
                            **{stage.name}**
                            - Count: {stage.count}
                            - % of Total: {stage.percentage:.1f}%
                            - Conversion: {stage.conversion_rate:.1f}%
                            """
                        )
                        st.progress(stage.percentage / 100)
            else:
                st.info("Start tracking applications to see conversion rates.")

        st.markdown("---")

        # Pipeline status breakdown
        st.subheader("Applications by Status")

        pipeline_counts = funnel.get_funnel().stages
        status_counts = {s.name.lower().replace(" ", "_"): s.count for s in pipeline_counts}

        # Also count terminal statuses
        from sqlalchemy import func, select
        from src.persistence.models import Application

        for status in ["rejected", "withdrawn", "ghosted"]:
            stmt = select(func.count(Application.id)).where(Application.status == status)
            count = session.execute(stmt).scalar() or 0
            status_counts[status] = count

        fig = create_pipeline_bar_chart(status_counts)
        st.plotly_chart(fig, width="stretch")

with tab2:
    st.subheader("Source Effectiveness")

    with get_session() as session:
        source_analytics = SourceAnalytics(session)
        comparison = source_analytics.get_source_comparison()

        if comparison["sources"]:
            # Metrics
            col1, col2, col3 = st.columns(3)

            with col1:
                best_response = comparison.get("best_response_rate")
                if best_response:
                    st.metric(
                        "Best Response Rate",
                        f"{best_response.source}: {best_response.response_rate:.1f}%",
                    )

            with col2:
                best_interview = comparison.get("best_interview_rate")
                if best_interview:
                    st.metric(
                        "Best Interview Rate",
                        f"{best_interview.source}: {best_interview.interview_rate:.1f}%",
                    )

            with col3:
                st.metric(
                    "Total Applications",
                    comparison.get("total_applications", 0),
                )

            st.markdown("---")

            # Comparison charts
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Response Rate by Source")
                fig = create_source_comparison_chart(
                    comparison["sources"], metric="response_rate"
                )
                st.plotly_chart(fig, width="stretch")

            with col2:
                st.subheader("Interview Rate by Source")
                fig = create_source_comparison_chart(
                    comparison["sources"], metric="interview_rate"
                )
                st.plotly_chart(fig, width="stretch")

            # Detailed table
            st.markdown("---")
            st.subheader("Detailed Source Statistics")

            import pandas as pd

            source_df = pd.DataFrame([
                {
                    "Source": s.source,
                    "Applications": s.total_applications,
                    "Responses": s.responses,
                    "Response Rate": f"{s.response_rate:.1f}%",
                    "Interviews": s.interviews,
                    "Interview Rate": f"{s.interview_rate:.1f}%",
                    "Offers": s.offers,
                    "Offer Rate": f"{s.offer_rate:.1f}%",
                }
                for s in comparison["sources"]
            ])

            st.dataframe(source_df, width="stretch", hide_index=True)

            # Recommendations
            st.markdown("---")
            st.subheader("Recommendations")

            best = source_analytics.get_best_source()
            if best and best.total_applications >= 5:
                st.success(
                    f"**{best.source}** is your best performing source with a "
                    f"{best.response_rate:.1f}% response rate. Consider focusing more efforts here."
                )

            # Find underperforming sources
            avg_response = sum(s.response_rate for s in comparison["sources"]) / len(comparison["sources"])
            underperforming = [
                s for s in comparison["sources"]
                if s.response_rate < avg_response / 2 and s.total_applications >= 3
            ]

            if underperforming:
                st.warning(
                    f"These sources are underperforming: "
                    f"{', '.join(s.source for s in underperforming)}. "
                    f"Consider adjusting your approach or reducing efforts here."
                )
        else:
            st.info("No source data available. Track the source when adding applications.")

with tab3:
    st.subheader("Resume Performance")

    with get_session() as session:
        resume_analytics = ResumeAnalytics(session)
        resume_stats = resume_analytics.get_resume_stats()

        if resume_stats:
            # Best resume
            best = resume_analytics.get_best_resume()

            if best:
                st.success(
                    f"**Best Performer:** {best.resume.name} "
                    f"with {best.response_rate:.1f}% response rate "
                    f"({best.total_applications} applications)"
                )

            st.markdown("---")

            # Comparison chart
            from dashboard.components.charts import create_resume_comparison_chart

            fig = create_resume_comparison_chart([
                {
                    "resume": s.resume,
                    "response_rate": s.response_rate,
                    "interview_rate": s.interview_rate,
                }
                for s in resume_stats
            ])
            st.plotly_chart(fig, width="stretch")

            st.markdown("---")

            # Detailed stats
            st.subheader("Resume Statistics")

            for stat in resume_stats:
                with st.expander(f"**{stat.resume.name}** (v{stat.resume.version})"):
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.metric("Applications", stat.total_applications)
                    with col2:
                        st.metric("Response Rate", f"{stat.response_rate:.1f}%")
                    with col3:
                        st.metric("Interview Rate", f"{stat.interview_rate:.1f}%")
                    with col4:
                        st.metric("Offers", stat.offers)

                    if stat.resume.key_changes:
                        st.markdown(f"**Key Changes:** {stat.resume.key_changes}")

                    if stat.resume.target_roles:
                        st.markdown(f"**Target Roles:** {', '.join(stat.resume.target_roles)}")

            # No resume tracking
            no_resume = resume_analytics.get_no_resume_stats()
            if no_resume["total"] > 0:
                st.warning(
                    f"You have {no_resume['total']} applications without resume tracking. "
                    f"Add resume info to get better insights."
                )
        else:
            st.info("No resume data available. Add resumes and track which one you use for each application.")

with tab4:
    st.subheader("Application Trends")

    with get_session() as session:
        funnel = FunnelAnalytics(session)

        # Time period selector
        weeks = st.slider("Weeks to analyze", min_value=4, max_value=16, value=8)

        # Weekly applications trend
        st.subheader("Weekly Applications")

        weekly_data = funnel.get_weekly_applications(weeks=weeks)

        if weekly_data and any(w["count"] > 0 for w in weekly_data):
            fig = create_trend_chart(
                weekly_data,
                x_key="week_start",
                y_key="count",
                title="Applications per Week",
                color="#3498db",
            )
            st.plotly_chart(fig, width="stretch")

            # Stats
            total_period = sum(w["count"] for w in weekly_data)
            avg_per_week = total_period / len(weekly_data) if weekly_data else 0
            max_week = max(weekly_data, key=lambda x: x["count"])
            min_week = min(weekly_data, key=lambda x: x["count"])

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total (Period)", total_period)
            with col2:
                st.metric("Avg per Week", f"{avg_per_week:.1f}")
            with col3:
                st.metric("Best Week", f"{max_week['count']} ({max_week['week_start']})")
            with col4:
                st.metric("Slowest Week", f"{min_week['count']} ({min_week['week_start']})")
        else:
            st.info("No application data for this period.")

        st.markdown("---")

        # Response time analysis
        st.subheader("Response Time Analysis")

        avg_rejection = funnel.get_average_time_to_rejection()

        if avg_rejection:
            col1, col2 = st.columns(2)

            with col1:
                st.metric(
                    "Avg Days to Rejection",
                    f"{avg_rejection:.0f} days",
                    help="Average time from application to rejection",
                )

            with col2:
                # Estimate active pipeline health
                active = funnel.get_active_pipeline_count()
                if active > 0 and avg_rejection:
                    old_threshold = datetime.now(timezone.utc) - timedelta(days=avg_rejection * 2)
                    # Count apps older than 2x avg rejection time
                    from sqlalchemy import select, func
                    from src.persistence.models import Application

                    stmt = select(func.count(Application.id)).where(
                        Application.applied_date < old_threshold,
                        Application.status.in_(["applied", "screening"]),
                    )
                    possibly_ghosted = session.execute(stmt).scalar() or 0

                    st.metric(
                        "Possibly Ghosted",
                        possibly_ghosted,
                        help=f"Applications > {avg_rejection * 2:.0f} days old with no response",
                    )
        else:
            st.info("Not enough rejection data to analyze response times.")

        # Weekly cadence recommendation
        st.markdown("---")
        st.subheader("Recommendations")

        if weekly_data:
            recent_weeks = weekly_data[-4:]  # Last 4 weeks
            recent_avg = sum(w["count"] for w in recent_weeks) / len(recent_weeks)

            if recent_avg < 5:
                st.warning(
                    f"Your recent application rate ({recent_avg:.1f}/week) is low. "
                    f"Consider increasing your application volume."
                )
            elif recent_avg > 20:
                st.info(
                    f"You're applying to {recent_avg:.1f} jobs/week. "
                    f"Make sure you're maintaining quality over quantity."
                )
            else:
                st.success(
                    f"Your application rate ({recent_avg:.1f}/week) is healthy. "
                    f"Keep up the consistent effort!"
                )
