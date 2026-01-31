"""Job card component for displaying job listings."""
import streamlit as st

from src.persistence.models import Job


def render_job_card(job: Job, show_actions: bool = True) -> None:
    """
    Render a job card with details and actions.

    Args:
        job: Job model instance
        show_actions: Whether to show action buttons
    """
    # Score styling
    if job.match_score and job.match_score >= 80:
        score_color = "#27ae60"
        score_emoji = "🔥"
        score_label = "Excellent Match"
    elif job.match_score and job.match_score >= 60:
        score_color = "#f39c12"
        score_emoji = "✨"
        score_label = "Good Match"
    else:
        score_color = "#3498db"
        score_emoji = "📋"
        score_label = "Potential Match"

    # Remote badge
    remote_badge = "🏠 Remote" if job.remote else ""

    # Salary display
    salary_str = ""
    if job.salary_min and job.salary_max:
        salary_str = f"💰 ${job.salary_min:,} - ${job.salary_max:,}"
    elif job.salary_min:
        salary_str = f"💰 ${job.salary_min:,}+"
    elif job.salary_max:
        salary_str = f"💰 Up to ${job.salary_max:,}"

    # Keywords
    keywords = job.matched_keywords or []
    keywords_str = ", ".join(keywords[:5]) if keywords else "No keywords matched"

    # Card container
    with st.container():
        st.markdown(
            f"""
            <div style="
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 1rem;
                margin-bottom: 1rem;
                background: white;
            ">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div>
                        <h3 style="margin: 0; color: #333;">
                            <a href="{job.url}" target="_blank" style="text-decoration: none; color: #333;">
                                {job.title}
                            </a>
                        </h3>
                        <p style="margin: 0.5rem 0; color: #666; font-size: 1.1rem;">
                            <strong>{job.company}</strong>
                            {f' • {job.location}' if job.location else ''}
                            {f' • {remote_badge}' if remote_badge else ''}
                        </p>
                    </div>
                    <div style="text-align: right;">
                        <span style="
                            background: {score_color};
                            color: white;
                            padding: 0.25rem 0.75rem;
                            border-radius: 20px;
                            font-weight: bold;
                        ">
                            {score_emoji} {job.match_score:.0f}%
                        </span>
                        <p style="margin: 0.25rem 0 0 0; font-size: 0.8rem; color: #666;">
                            {score_label}
                        </p>
                    </div>
                </div>
                <div style="margin-top: 0.75rem;">
                    {f'<span style="margin-right: 1rem;">{salary_str}</span>' if salary_str else ''}
                    <span style="color: #666;">📍 {job.source}</span>
                </div>
                <div style="margin-top: 0.5rem; color: #888; font-size: 0.9rem;">
                    <strong>Keywords:</strong> {keywords_str}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if show_actions:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("Apply 🚀", key=f"apply_{job.id}"):
                    st.session_state[f"apply_job_{job.id}"] = True

            with col2:
                if st.button("Save ⭐", key=f"save_{job.id}"):
                    st.session_state[f"saved_job_{job.id}"] = True
                    st.success("Saved!")

            with col3:
                if st.button("Dismiss 👋", key=f"dismiss_{job.id}"):
                    st.session_state[f"dismissed_job_{job.id}"] = True

            with col4:
                if st.button("Details 📄", key=f"details_{job.id}"):
                    st.session_state[f"show_details_{job.id}"] = not st.session_state.get(
                        f"show_details_{job.id}", False
                    )

            # Show details if expanded
            if st.session_state.get(f"show_details_{job.id}", False):
                if job.description:
                    with st.expander("Job Description", expanded=True):
                        st.markdown(job.description[:2000])
                        if len(job.description) > 2000:
                            st.markdown("_...description truncated_")


def render_job_card_compact(job: Job) -> None:
    """
    Render a compact job card for lists.

    Args:
        job: Job model instance
    """
    score_emoji = "🔥" if job.match_score >= 80 else "✨" if job.match_score >= 60 else "📋"
    remote_str = " 🏠" if job.remote else ""

    st.markdown(
        f"""
        {score_emoji} **[{job.title}]({job.url})** | {job.company}{remote_str}
        | Score: {job.match_score:.0f}% | {job.source}
        """
    )
