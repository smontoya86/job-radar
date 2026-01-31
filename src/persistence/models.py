"""SQLAlchemy models for Job Radar."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Job(Base):
    """Job posting from radar."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String)
    description = Column(Text)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    url = Column(String, nullable=False)
    apply_url = Column(String)
    source = Column(String, nullable=False)  # indeed, linkedin, etc.
    remote = Column(Boolean, default=False)

    # Matching
    match_score = Column(Float)
    matched_keywords = Column(JSON)  # List of matched keywords
    fingerprint = Column(String)  # For deduplication

    # Timestamps
    posted_date = Column(DateTime)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    notified_at = Column(DateTime)

    # Status: new, applied, rejected, saved, dismissed
    status = Column(String, default="new")

    # Relationships
    applications = relationship("Application", back_populates="job")

    def __repr__(self) -> str:
        return f"<Job {self.company} - {self.title}>"


class Resume(Base):
    """Resume version for tracking."""

    __tablename__ = "resumes"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)  # "AI PM v3", "Search Focus"
    file_path = Column(String)
    version = Column(Integer, default=1)
    target_roles = Column(JSON)  # JSON array of target roles
    key_changes = Column(Text)  # What's different from previous
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    applications = relationship("Application", back_populates="resume")

    def __repr__(self) -> str:
        return f"<Resume {self.name} v{self.version}>"


class Application(Base):
    """Job application tracking."""

    __tablename__ = "applications"

    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True)
    company = Column(String, nullable=False)
    position = Column(String, nullable=False)

    # Application details
    applied_date = Column(DateTime, nullable=False)
    source = Column(String)  # linkedin, company_site, referral
    resume_id = Column(String, ForeignKey("resumes.id"), nullable=True)
    cover_letter_used = Column(Boolean, default=False)
    referral_name = Column(String)
    job_url = Column(String)  # URL to job posting (for manual entry)
    job_description = Column(Text)  # Job description text (for analysis)

    # Status tracking
    # Statuses: applied, phone_screen, interviewing, offer, accepted, rejected, withdrawn, ghosted
    status = Column(String, nullable=False, default="applied")
    last_status_change = Column(DateTime, default=datetime.utcnow)

    # Interview tracking
    interview_rounds = Column(Integer, default=0)
    next_interview_date = Column(DateTime)
    interview_notes = Column(Text)
    current_stage = Column(String)  # More specific: "Phone Screen", "HM Interview", etc.

    # Outcome
    rejected_at = Column(String)  # Stage: resume, phone_screen, onsite, offer
    rejection_reason = Column(Text)
    offer_amount = Column(Integer)
    offer_equity = Column(String)

    # Metadata
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    job = relationship("Job", back_populates="applications")
    resume = relationship("Resume", back_populates="applications")
    interviews = relationship("Interview", back_populates="application")
    email_imports = relationship("EmailImport", back_populates="application")

    def __repr__(self) -> str:
        return f"<Application {self.company} - {self.position} ({self.status})>"


class Interview(Base):
    """Interview tracking."""

    __tablename__ = "interviews"

    # Standard interview types for tracking
    INTERVIEW_TYPES = [
        "Phone Screen",
        "Recruiter Screen",
        "HM Interview",
        "Technical",
        "Product Sense",
        "Product Strategy",
        "Case Study",
        "System Design",
        "Behavioral",
        "Take Home",
        "Panel",
        "Final Round",
        "Other",
    ]

    id = Column(String, primary_key=True, default=generate_uuid)
    application_id = Column(String, ForeignKey("applications.id"), nullable=False)
    round = Column(Integer, default=1)  # 1, 2, 3...
    type = Column(String)  # One of INTERVIEW_TYPES
    scheduled_at = Column(DateTime)
    interviewers = Column(JSON)  # JSON array of interviewer names
    duration_minutes = Column(Integer)
    topics = Column(JSON)  # JSON array of topics covered
    outcome = Column(String)  # passed, failed, pending
    feedback = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    application = relationship("Application", back_populates="interviews")

    def __repr__(self) -> str:
        return f"<Interview {self.application_id} Round {self.round}>"


class EmailImport(Base):
    """Imported emails from Gmail."""

    __tablename__ = "email_imports"

    id = Column(String, primary_key=True, default=generate_uuid)
    gmail_message_id = Column(String, unique=True, nullable=False)
    subject = Column(String)
    from_address = Column(String)
    received_at = Column(DateTime)
    email_type = Column(String)  # confirmation, rejection, interview_invite, offer
    application_id = Column(String, ForeignKey("applications.id"), nullable=True)
    parsed_data = Column(JSON)  # Extracted data from email
    imported_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)

    # Relationships
    application = relationship("Application", back_populates="email_imports")

    def __repr__(self) -> str:
        return f"<EmailImport {self.email_type}: {self.subject}>"


class StatusHistory(Base):
    """Track status changes for applications."""

    __tablename__ = "status_history"

    id = Column(String, primary_key=True, default=generate_uuid)
    application_id = Column(String, ForeignKey("applications.id"), nullable=False)
    old_status = Column(String)
    new_status = Column(String, nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)
