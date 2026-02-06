"""Applications page - Track and manage job applications."""
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path (required for Streamlit)
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
import pandas as pd

from dashboard.common import get_session
from src.persistence.models import Application, Resume, Interview
from src.tracking.application_service import ApplicationService
from src.tracking.resume_service import ResumeService

# Simplified statuses
ALL_STATUSES = ["applied", "phone_screen", "interviewing", "offer", "accepted", "rejected", "withdrawn", "ghosted"]
ACTIVE_STATUSES = ["applied", "phone_screen", "interviewing", "offer"]

st.set_page_config(page_title="Applications | Job Radar", page_icon="📋", layout="wide")

st.title("📋 Application Tracker")

# Tabs
tab1, tab2, tab3 = st.tabs(["All Applications", "Add New", "Manage Resumes"])

with tab1:
    st.subheader("Your Applications")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All"] + ALL_STATUSES,
        )

    with col2:
        company_search = st.text_input("Search Company")

    with col3:
        sort_by = st.selectbox("Sort By", ["Applied Date", "Company", "Status", "Last Update"])

    with get_session() as session:
        app_service = ApplicationService(session)

        # Get applications
        status = None if status_filter == "All" else status_filter
        applications = app_service.get_all_applications(
            status=status,
            company=company_search if company_search else None,
            limit=200,
        )

        # Sort
        if sort_by == "Applied Date":
            applications.sort(key=lambda x: x.applied_date or datetime.min, reverse=True)
        elif sort_by == "Company":
            applications.sort(key=lambda x: x.company.lower())
        elif sort_by == "Status":
            applications.sort(key=lambda x: x.status)
        elif sort_by == "Last Update":
            applications.sort(key=lambda x: x.last_status_change or datetime.min, reverse=True)

        # Stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total", len(applications))
        with col2:
            active = sum(1 for a in applications if a.status in ACTIVE_STATUSES)
            st.metric("Active", active)
        with col3:
            interviewing = sum(1 for a in applications if a.status in ["phone_screen", "interviewing"])
            st.metric("Interviewing", interviewing)
        with col4:
            offers = sum(1 for a in applications if a.status in ["offer", "accepted"])
            st.metric("Offers", offers)

        st.markdown("---")

        if not applications:
            st.info("No applications found. Add your first application!")
        else:
            for app in applications:
                # Show current stage in title if available
                stage_info = f" → {app.current_stage}" if app.current_stage else ""
                with st.expander(f"**{app.company}** - {app.position} | {app.status.replace('_', ' ').title()}{stage_info}"):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**Position:** {app.position}")
                        st.markdown(f"**Applied:** {app.applied_date.strftime('%B %d, %Y') if app.applied_date else 'N/A'}")
                        st.markdown(f"**Source:** {app.source or 'Not specified'}")

                        if app.referral_name:
                            st.markdown(f"**Referral:** {app.referral_name}")

                        if app.current_stage:
                            st.markdown(f"**Current Stage:** {app.current_stage}")

                        if app.interview_rounds > 0:
                            st.markdown(f"**Interview Rounds:** {app.interview_rounds}")

                        if app.next_interview_date:
                            st.markdown(f"**Next Interview:** {app.next_interview_date.strftime('%B %d, %Y %I:%M %p')}")

                        if app.notes:
                            st.markdown(f"**Notes:** {app.notes}")

                    with col2:
                        # Status update
                        new_status = st.selectbox(
                            "Update Status",
                            ALL_STATUSES,
                            index=ALL_STATUSES.index(app.status) if app.status in ALL_STATUSES else 0,
                            key=f"status_{app.id}",
                        )

                        if st.button("Update", key=f"update_{app.id}"):
                            app_service.update_status(app.id, new_status)
                            st.success("Status updated!")
                            st.rerun()

                        # Add interview
                        if app.status in ACTIVE_STATUSES:
                            if st.button("Add Interview", key=f"interview_{app.id}"):
                                st.session_state[f"add_interview_{app.id}"] = True

                    # Add interview form
                    if st.session_state.get(f"add_interview_{app.id}", False):
                        st.markdown("---")
                        st.markdown("**Add Interview**")

                        int_col1, int_col2 = st.columns(2)
                        with int_col1:
                            interview_type = st.selectbox(
                                "Interview Type",
                                Interview.INTERVIEW_TYPES,
                                key=f"int_type_{app.id}",
                            )
                            interview_date = st.date_input("Date", key=f"int_date_{app.id}")
                            interview_time = st.time_input("Time", key=f"int_time_{app.id}")

                        with int_col2:
                            interviewers = st.text_input("Interviewers (comma separated)", key=f"int_people_{app.id}")
                            duration = st.number_input("Duration (minutes)", value=60, key=f"int_duration_{app.id}")
                            interview_notes = st.text_area("Notes", key=f"int_notes_{app.id}", height=100)

                        if st.button("Save Interview", key=f"save_int_{app.id}"):
                            scheduled_at = datetime.combine(interview_date, interview_time)
                            result = app_service.add_interview(
                                application_id=app.id,
                                interview_type=interview_type,
                                scheduled_at=scheduled_at,
                                interviewers=[i.strip() for i in interviewers.split(",")] if interviewers else None,
                                duration_minutes=int(duration),
                                notes=interview_notes if interview_notes else None,
                            )
                            if result:
                                st.success("Interview added! Status updated based on interview type.")
                            else:
                                st.warning("Cannot add interview to a closed application.")
                            st.session_state[f"add_interview_{app.id}"] = False
                            st.rerun()

with tab2:
    st.subheader("Add New Application")

    with st.form("new_application"):
        col1, col2 = st.columns(2)

        with col1:
            company = st.text_input("Company *")
            position = st.text_input("Position *")
            applied_date = st.date_input("Applied Date", value=datetime.now())
            source = st.selectbox(
                "Source",
                ["linkedin", "company_site", "referral", "indeed", "glassdoor", "other"],
            )

        with col2:
            referral_name = st.text_input("Referral Name (if applicable)")
            cover_letter = st.checkbox("Cover Letter Used")

            # Resume selection
            with get_session() as session:
                resume_service = ResumeService(session)
                resumes = resume_service.get_all_resumes(active_only=True)
                resume_options = ["None"] + [r.name for r in resumes]
                resume_selection = st.selectbox("Resume Used", resume_options)

            notes = st.text_area("Notes")

        submitted = st.form_submit_button("Add Application")

        if submitted:
            if not company or not position:
                st.error("Company and Position are required.")
            else:
                with get_session() as session:
                    app_service = ApplicationService(session)

                    # Get resume ID if selected
                    resume_id = None
                    if resume_selection != "None":
                        resume_service = ResumeService(session)
                        resumes = resume_service.get_all_resumes(active_only=True)
                        selected_resume = next((r for r in resumes if r.name == resume_selection), None)
                        if selected_resume:
                            resume_id = selected_resume.id

                    app_service.create_application(
                        company=company,
                        position=position,
                        applied_date=datetime.combine(applied_date, datetime.min.time()),
                        source=source,
                        resume_id=resume_id,
                        notes=notes,
                    )

                    st.success(f"Added application to {company}!")
                    st.rerun()

with tab3:
    st.subheader("Resume Versions")

    with get_session() as session:
        resume_service = ResumeService(session)
        resumes = resume_service.get_all_resumes()

        if resumes:
            for resume in resumes:
                stats = resume_service.get_resume_stats(resume.id)

                with st.expander(f"**{resume.name}** (v{resume.version}) {'✅ Active' if resume.is_active else '❌ Inactive'}"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Created:** {resume.created_at.strftime('%B %d, %Y') if resume.created_at else 'N/A'}")
                        if resume.target_roles:
                            st.markdown(f"**Target Roles:** {', '.join(resume.target_roles)}")
                        if resume.key_changes:
                            st.markdown(f"**Key Changes:** {resume.key_changes}")
                        if resume.file_path:
                            st.markdown(f"**File:** {resume.file_path}")

                    with col2:
                        st.metric("Applications", stats["total_applications"])
                        st.metric("Response Rate", f"{stats['response_rate']:.1f}%")
                        st.metric("Interview Rate", f"{stats['interview_rate']:.1f}%")

                    # Toggle active status
                    if resume.is_active:
                        if st.button("Deactivate", key=f"deactivate_{resume.id}"):
                            resume_service.deactivate_resume(resume.id)
                            st.rerun()
                    else:
                        if st.button("Activate", key=f"activate_{resume.id}"):
                            resume_service.update_resume(resume.id, is_active=True)
                            st.rerun()

        st.markdown("---")
        st.subheader("Add New Resume")

        with st.form("new_resume"):
            name = st.text_input("Resume Name (e.g., 'AI PM v3')")
            file_path = st.text_input("File Path (optional)")
            target_roles = st.text_input("Target Roles (comma separated)")
            key_changes = st.text_area("Key Changes from Previous Version")

            if st.form_submit_button("Add Resume"):
                if not name:
                    st.error("Resume name is required.")
                else:
                    with get_session() as session:
                        resume_service = ResumeService(session)
                        resume_service.create_resume(
                            name=name,
                            file_path=file_path if file_path else None,
                            target_roles=[r.strip() for r in target_roles.split(",")] if target_roles else None,
                            key_changes=key_changes if key_changes else None,
                        )
                        st.success(f"Added resume: {name}")
                        st.rerun()
