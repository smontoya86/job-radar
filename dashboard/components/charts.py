"""Chart components for analytics."""
from typing import Optional

import plotly.express as px
import plotly.graph_objects as go

from src.analytics.funnel import FunnelData
from src.analytics.source_analysis import SourceStats


def create_funnel_chart(funnel_data: FunnelData) -> go.Figure:
    """
    Create a funnel chart for application stages.

    Args:
        funnel_data: FunnelData from analytics

    Returns:
        Plotly figure
    """
    fig = go.Figure(
        go.Funnel(
            y=[stage.name for stage in funnel_data.stages],
            x=[stage.count for stage in funnel_data.stages],
            textposition="inside",
            textinfo="value+percent initial",
            marker=dict(
                color=[
                    "#3498db",  # Applied
                    "#9b59b6",  # Screening
                    "#8e44ad",  # Phone Screen
                    "#e67e22",  # Interview
                    "#f39c12",  # Onsite
                    "#27ae60",  # Offer
                    "#2ecc71",  # Accepted
                ]
            ),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Count: %{x}<br>"
                "Conversion: %{percentInitial:.1%}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="Application Funnel",
        height=450,
        margin=dict(l=20, r=20, t=50, b=20),
        font=dict(size=14),
    )

    return fig


def create_trend_chart(
    data: list[dict],
    x_key: str = "week_start",
    y_key: str = "count",
    title: str = "Weekly Trend",
    color: str = "#3498db",
) -> go.Figure:
    """
    Create a trend line chart.

    Args:
        data: List of data points with x and y values
        x_key: Key for x-axis values
        y_key: Key for y-axis values
        title: Chart title
        color: Line color

    Returns:
        Plotly figure
    """
    if not data:
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    x_values = [d[x_key] for d in data]
    y_values = [d[y_key] for d in data]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="lines+markers",
            line=dict(color=color, width=3),
            marker=dict(size=10),
            fill="tozeroy",
            fillcolor=f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1)",
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Week",
        yaxis_title="Count",
        height=350,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False,
    )

    return fig


def create_source_comparison_chart(
    source_stats: list[SourceStats],
    metric: str = "response_rate",
) -> go.Figure:
    """
    Create a bar chart comparing sources.

    Args:
        source_stats: List of SourceStats
        metric: Metric to compare (response_rate, interview_rate, offer_rate)

    Returns:
        Plotly figure
    """
    if not source_stats:
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    # Get metric values
    sources = [s.source for s in source_stats]
    values = [getattr(s, metric) for s in source_stats]

    # Color based on value
    colors = [
        "#27ae60" if v >= 50 else "#f39c12" if v >= 25 else "#e74c3c" for v in values
    ]

    metric_labels = {
        "response_rate": "Response Rate (%)",
        "interview_rate": "Interview Rate (%)",
        "offer_rate": "Offer Rate (%)",
    }

    fig = go.Figure(
        go.Bar(
            x=sources,
            y=values,
            marker_color=colors,
            text=[f"{v:.1f}%" for v in values],
            textposition="outside",
        )
    )

    fig.update_layout(
        title=f"Source Comparison: {metric_labels.get(metric, metric)}",
        xaxis_title="Source",
        yaxis_title=metric_labels.get(metric, metric),
        height=400,
        margin=dict(l=20, r=20, t=50, b=20),
        yaxis=dict(range=[0, max(values) * 1.2] if values else [0, 100]),
    )

    return fig


def create_resume_comparison_chart(
    resume_stats: list[dict],
) -> go.Figure:
    """
    Create a grouped bar chart comparing resume performance.

    Args:
        resume_stats: List of resume statistics

    Returns:
        Plotly figure
    """
    if not resume_stats:
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    names = [s["resume"].name for s in resume_stats]
    response_rates = [s["response_rate"] for s in resume_stats]
    interview_rates = [s["interview_rate"] for s in resume_stats]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Response Rate",
            x=names,
            y=response_rates,
            marker_color="#3498db",
            text=[f"{v:.1f}%" for v in response_rates],
            textposition="outside",
        )
    )

    fig.add_trace(
        go.Bar(
            name="Interview Rate",
            x=names,
            y=interview_rates,
            marker_color="#27ae60",
            text=[f"{v:.1f}%" for v in interview_rates],
            textposition="outside",
        )
    )

    fig.update_layout(
        title="Resume Performance Comparison",
        xaxis_title="Resume Version",
        yaxis_title="Rate (%)",
        barmode="group",
        height=400,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    return fig


def create_pipeline_bar_chart(status_counts: dict[str, int]) -> go.Figure:
    """
    Create a horizontal bar chart for pipeline status.

    Args:
        status_counts: Dictionary of status -> count

    Returns:
        Plotly figure
    """
    # Define status order and colors
    status_order = [
        "applied",
        "screening",
        "phone_screen",
        "interview",
        "onsite",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "ghosted",
    ]

    status_colors = {
        "applied": "#3498db",
        "screening": "#9b59b6",
        "phone_screen": "#8e44ad",
        "interview": "#e67e22",
        "onsite": "#f39c12",
        "offer": "#27ae60",
        "accepted": "#2ecc71",
        "rejected": "#e74c3c",
        "withdrawn": "#95a5a6",
        "ghosted": "#7f8c8d",
    }

    # Filter to statuses with counts
    statuses = [s for s in status_order if status_counts.get(s, 0) > 0]
    counts = [status_counts.get(s, 0) for s in statuses]
    colors = [status_colors.get(s, "#3498db") for s in statuses]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=[s.replace("_", " ").title() for s in statuses],
            orientation="h",
            marker_color=colors,
            text=counts,
            textposition="outside",
        )
    )

    fig.update_layout(
        title="Applications by Status",
        xaxis_title="Count",
        height=400,
        margin=dict(l=100, r=20, t=50, b=20),
    )

    return fig
