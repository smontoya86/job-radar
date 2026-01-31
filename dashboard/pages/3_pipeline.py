"""Pipeline page - Kanban-style view of applications."""
import sys
from pathlib import Path

# Add project root to path (required for Streamlit)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

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
        count = len(apps_by_status.get(status, []))
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
                    <p style="margin: 0;">{label}</p>
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
                f"""
                <div style="
                    background: {color}20;
                    border-top: 4px solid {color};
                    padding: 0.5rem;
                    border-radius: 8px;
                    margin-bottom: 0.5rem;
                ">
                    <strong>{label}</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )

            stage_apps = apps_by_status.get(status, [])

            if not stage_apps:
                st.markdown("_No applications_")
            else:
                for app in stage_apps[:10]:  # Limit displayed
                    # Card for each application
                    st.markdown(
                        f"""
                        <div style="
                            background: white;
                            border: 1px solid #e0e0e0;
                            border-left: 4px solid {color};
                            padding: 0.5rem;
                            border-radius: 4px;
                            margin-bottom: 0.5rem;
                            font-size: 0.9rem;
                        ">
                            <strong>{app.company}</strong><br>
                            <span style="color: #666;">{app.position[:25]}{'...' if len(app.position) > 25 else ''}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

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
                with st.expander(f"View {label}"):
                    for app in stage_apps[:20]:
                        st.markdown(f"- **{app.company}** - {app.position}")

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

    # Conversion funnel
    st.markdown("---")
    st.markdown("### Conversion Funnel")

    if total > 0:
        import plotly.graph_objects as go

        funnel_data = []
        for status, label, _ in PIPELINE_STAGES:
            # Count apps at this stage or beyond
            idx = [s[0] for s in PIPELINE_STAGES].index(status)
            count = sum(
                len(apps_by_status.get(s[0], []))
                for s in PIPELINE_STAGES[idx:]
            )
            count += len(apps_by_status.get("accepted", []))  # Include accepted
            funnel_data.append((label, count))

        fig = go.Figure(
            go.Funnel(
                y=[d[0] for d in funnel_data],
                x=[d[1] for d in funnel_data],
                textposition="inside",
                textinfo="value+percent initial",
                marker=dict(color=[s[2] for s in PIPELINE_STAGES]),
            )
        )

        fig.update_layout(
            height=400,
            margin=dict(l=20, r=20, t=20, b=20),
        )

        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Add applications to see your conversion funnel.")
