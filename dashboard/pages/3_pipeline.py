"""Pipeline page - Kanban-style view of applications."""
import sys
from pathlib import Path

# Add project root to path (required for Streamlit)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import html

import streamlit as st
from sqlalchemy import select

from dashboard.common import get_session
from src.persistence.models import Application
from src.tracking.application_service import ApplicationService

st.set_page_config(page_title="Pipeline | Job Radar", page_icon="📊", layout="wide")

st.title("📊 Application Pipeline")
st.markdown("Visualize your application funnel and track progress.")

# Define pipeline stages (simplified)
# applied -> phone_screen -> interviewing -> offer
PIPELINE_STAGES = [
    ("applied", "Applied", "#3498db"),
    ("phone_screen", "Phone Screen", "#9b59b6"),
    ("interviewing", "Interviewing", "#e67e22"),
    ("offer", "Offer", "#27ae60"),
]

CLOSED_STAGES = [
    ("accepted", "Accepted", "#2ecc71"),
    ("rejected", "Rejected", "#e74c3c"),
    ("withdrawn", "Withdrawn", "#95a5a6"),
    ("ghosted", "Ghosted", "#7f8c8d"),
]

with get_session() as session:
    app_service = ApplicationService(session)

    # Get all applications
    applications = app_service.get_all_applications(limit=500)

    # Group by status
    apps_by_status = {}
    for app in applications:
        if app.status not in apps_by_status:
            apps_by_status[app.status] = []
        apps_by_status[app.status].append(app)

    # Pipeline metrics
    st.markdown("### Pipeline Overview")

    metrics_cols = st.columns(len(PIPELINE_STAGES))
    for i, (status, label, color) in enumerate(PIPELINE_STAGES):
        stage_apps = apps_by_status.get(status, [])
        count = len(stage_apps)
        with metrics_cols[i]:
            st.markdown(
                f"""
                <div style="
                    background: {color};
                    color: white;
                    padding: 1rem;
                    border-radius: 8px;
                    text-align: center;
                ">
                    <h2 style="margin: 0;">{count}</h2>
                    <p style="margin: 0; font-weight: bold;">{label}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Kanban board
    st.markdown("### Pipeline Board")

    # Create columns for each stage
    cols = st.columns(len(PIPELINE_STAGES))

    for col_idx, (status, label, color) in enumerate(PIPELINE_STAGES):
        with cols[col_idx]:
            st.markdown(
                f'<div style="background:{color}20;border-top:4px solid {color};padding:0.5rem;border-radius:8px;margin-bottom:0.5rem"><strong>{label}</strong></div>',
                unsafe_allow_html=True,
            )

            stage_apps = apps_by_status.get(status, [])

            if not stage_apps:
                st.markdown("_No applications_")
            else:
                for app in stage_apps[:10]:  # Limit displayed
                    # Format applied date
                    applied_str = ""
                    if app.applied_date:
                        applied_str = app.applied_date.strftime("%b %d")

                    # Stage detail (e.g. "Phone Screen" vs just the status)
                    stage_detail = html.escape(app.current_stage or "")

                    company_safe = html.escape(app.company)
                    position_safe = app.position[:40] + "..." if len(app.position) > 40 else app.position
                    position_safe = html.escape(position_safe)

                    # Card for each application
                    stage_badge = ""
                    if stage_detail:
                        stage_badge = f'<span style="background:{color}22;color:{color};font-size:0.7rem;padding:1px 6px;border-radius:3px;font-weight:600">{stage_detail}</span>'

                    card_html = (
                        f'<div style="background:white;border:1px solid #e0e0e0;border-left:4px solid {color};padding:0.75rem;border-radius:6px;margin-bottom:0.5rem">'
                        f'<div style="font-weight:700;font-size:1.05rem;margin-bottom:2px;color:#111">{company_safe}</div>'
                        f'<div style="color:#444;font-size:0.85rem;margin-bottom:4px">{position_safe}</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<span style="color:#999;font-size:0.75rem">{applied_str}</span>'
                        f'{stage_badge}</div></div>'
                    )
                    st.markdown(card_html, unsafe_allow_html=True)

                    # Quick actions
                    action_col1, action_col2 = st.columns(2)

                    # Move forward button
                    current_idx = [s[0] for s in PIPELINE_STAGES].index(status) if status in [s[0] for s in PIPELINE_STAGES] else -1

                    with action_col1:
                        if current_idx < len(PIPELINE_STAGES) - 1:
                            next_status = PIPELINE_STAGES[current_idx + 1][0]
                            if st.button("→", key=f"fwd_{app.id}", help=f"Move to {PIPELINE_STAGES[current_idx + 1][1]}"):
                                app_service.update_status(app.id, next_status)
                                st.rerun()

                    with action_col2:
                        if st.button("✗", key=f"rej_{app.id}", help="Mark as rejected"):
                            app_service.update_status(app.id, "rejected")
                            st.rerun()

                if len(stage_apps) > 10:
                    st.markdown(f"_+{len(stage_apps) - 10} more_")

    st.markdown("---")

    # Closed applications
    st.markdown("### Closed Applications")

    closed_cols = st.columns(len(CLOSED_STAGES))

    for col_idx, (status, label, color) in enumerate(CLOSED_STAGES):
        with closed_cols[col_idx]:
            stage_apps = apps_by_status.get(status, [])

            st.markdown(
                f"""
                <div style="
                    background: {color}20;
                    border-top: 4px solid {color};
                    padding: 0.5rem;
                    border-radius: 8px;
                    text-align: center;
                ">
                    <strong>{label}</strong>: {len(stage_apps)}
                </div>
                """,
                unsafe_allow_html=True,
            )

            if stage_apps:
                with st.expander(f"View {label} ({len(stage_apps)})"):
                    for app in stage_apps[:20]:
                        # Format dates
                        applied_str = app.applied_date.strftime("%b %d") if app.applied_date else ""
                        position_short = app.position[:35] + "..." if len(app.position) > 35 else app.position
                        st.markdown(
                            f"""
                            <div style="
                                padding: 0.3rem 0;
                                border-bottom: 1px solid #eee;
                            ">
                                <strong>{html.escape(app.company)}</strong> - {html.escape(position_short)}
                                <span style="color: #999; font-size: 0.8rem; float: right;">{applied_str}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    if len(stage_apps) > 20:
                        st.markdown(f"_+{len(stage_apps) - 20} more_")

    # Pipeline summary
    st.markdown("---")
    st.markdown("### Pipeline Summary")

    total = len(applications)
    active = sum(
        len(apps_by_status.get(s[0], []))
        for s in PIPELINE_STAGES
    )
    closed = total - active

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Applications", total)

    with col2:
        st.metric("Active in Pipeline", active)

    with col3:
        st.metric("Closed", closed)

    with col4:
        rejection_rate = (
            len(apps_by_status.get("rejected", [])) / total * 100
            if total > 0
            else 0
        )
        st.metric("Rejection Rate", f"{rejection_rate:.1f}%")

    # Conversion funnel (uses FunnelAnalytics for highest-stage-reached consistency)
    st.markdown("---")
    st.markdown("### Conversion Funnel")

    if total > 0:
        from src.analytics.funnel import FunnelAnalytics
        from dashboard.components.charts import create_funnel_chart

        funnel_analytics = FunnelAnalytics(session)
        funnel_result = funnel_analytics.get_funnel()

        if funnel_result.total_applications > 0:
            fig = create_funnel_chart(funnel_result)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Add applications to see your conversion funnel.")
    else:
        st.info("Add applications to see your conversion funnel.")
