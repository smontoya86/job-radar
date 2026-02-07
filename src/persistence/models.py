"""SQLAlchemy models for Job Radar."""
import re
import uuid
from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def normalize_company_key(name: str) -> str:
    """Normalize company name to a canonical key for fast matching.

    Lowercases, strips whitespace, and removes common suffixes like
    Inc, LLC, Corp, Ltd, Co so that "Stripe, Inc." and "Stripe" match.
    """
    if not name:
        return ""
    key = name.lower().strip()
    # Remove trailing punctuation and common suffixes
    key = re.sub(r"[.,;:!]+$", "", key)
    for suffix in (" inc", " llc", " corp", " ltd", " co", " company"):
        if key.endswith(suffix):
            key = key[: -len(suffix)].rstrip()
    # Strip punctuation again (e.g., "Stripe, Inc." -> "stripe," after suffix removal)
    key = re.sub(r"[.,;:!]+$", "", key)
    return key


def normalize_company_key_fuzzy(name: str) -> str:
    """Create a fuzzy matching key by stripping all non-alphanumeric chars.

    Handles cases like 'Fetchrewards' vs 'Fetch Rewards' and
    'Maven AGI' vs 'Maven A.G.I.' by removing spaces and punctuation.
    """
    key = normalize_company_key(name)
    return re.sub(r"[^a-z0-9]", "", key)


from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
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


class User(Base):
    """User account for multi-tenant SaaS."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)  # Null for OAuth-only users
    google_id = Column(String, unique=True, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)

    # Billing tier (for future monetization)
    tier = Column(String, default="free")  # free, pro, enterprise

    # Login tracking
    last_login = Column(DateTime, nullable=True)
    login_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=utcnow)

    # Relationships
    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")
    applications = relationship(
        "Application", back_populates="user", cascade="all, delete-orphan"
    )
    resumes = relationship(
        "Resume", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.email})>"


class UserProfile(Base):
    """User profile storing job search preferences (replaces profile.yaml)."""

    __tablename__ = "user_profiles"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)

    # Job search criteria (JSON for flexibility)
    target_titles = Column(JSON, default=dict)  # {"primary": [...], "secondary": [...]}
    required_keywords = Column(JSON, default=dict)  # {"primary": [...], "secondary": [...]}
    negative_keywords = Column(JSON, default=list)  # [...]
    compensation = Column(JSON, default=dict)  # {"min_salary": X, "max_salary": Y}
    location = Column(JSON, default=dict)  # {"preferred": [...], "remote_only": bool}
    target_companies = Column(JSON, default=dict)  # {"tier1": [...], "tier2": [...]}

    # Notification preferences
    in_app_notifications = Column(Boolean, default=True)
    email_digest_enabled = Column(Boolean, default=True)
    email_digest_frequency = Column(String, default="daily")  # daily, weekly, never
    slack_notifications = Column(Boolean, default=False)  # Off until connected
    min_score_for_notification = Column(Integer, default=60)

    # Integration tokens (encrypted at rest)
    slack_webhook_url = Column(String, nullable=True)
    gmail_token = Column(Text, nullable=True)  # Encrypted OAuth token

    # Timestamps
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    user = relationship("User", back_populates="profile")

    def __repr__(self) -> str:
        return f"<UserProfile user_id={self.user_id}>"


class Job(Base):
    """Job posting from radar."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Multi-tenant
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    company_key = Column(String, index=True)  # Normalized for fast matching
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
    discovered_at = Column(DateTime, default=utcnow)
    notified_at = Column(DateTime)

    # Status: new, applied, rejected, saved, dismissed
    status = Column(String, default="new")

    # Relationships
    user = relationship("User", back_populates="jobs")
    applications = relationship("Application", back_populates="job")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.company and not self.company_key:
            self.company_key = normalize_company_key(self.company)

    def __repr__(self) -> str:
        return f"<Job {self.company} - {self.title}>"


class Resume(Base):
    """Resume version for tracking."""

    __tablename__ = "resumes"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Multi-tenant
    name = Column(String, nullable=False)  # "AI PM v3", "Search Focus"
    file_path = Column(String)
    version = Column(Integer, default=1)
    target_roles = Column(JSON)  # JSON array of target roles
    key_changes = Column(Text)  # What's different from previous
    created_at = Column(DateTime, default=utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="resumes")
    applications = relationship("Application", back_populates="resume")

    def __repr__(self) -> str:
        return f"<Resume {self.name} v{self.version}>"


class Application(Base):
    """Job application tracking."""

    __tablename__ = "applications"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Multi-tenant
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True)
    company = Column(String, nullable=False)
    company_key = Column(String, index=True)  # Normalized for fast matching
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
    last_status_change = Column(DateTime, default=utcnow)

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
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    user = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")
    resume = relationship("Resume", back_populates="applications")
    interviews = relationship("Interview", back_populates="application")
    email_imports = relationship("EmailImport", back_populates="application")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.company and not self.company_key:
            self.company_key = normalize_company_key(self.company)

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
    created_at = Column(DateTime, default=utcnow)

    # Relationships
    application = relationship("Application", back_populates="interviews")

    def __repr__(self) -> str:
        return f"<Interview {self.application_id} Round {self.round}>"


class EmailImport(Base):
    """Imported emails from Gmail."""

    __tablename__ = "email_imports"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Multi-tenant
    gmail_message_id = Column(String, unique=True, nullable=False)
    subject = Column(String)
    from_address = Column(String)
    received_at = Column(DateTime)
    email_type = Column(String)  # confirmation, rejection, interview_invite, offer
    application_id = Column(String, ForeignKey("applications.id"), nullable=True)
    parsed_data = Column(JSON)  # Extracted data from email
    imported_at = Column(DateTime, default=utcnow)
    processed = Column(Boolean, default=False)

    # Relationships
    application = relationship("Application", back_populates="email_imports")

    def __repr__(self) -> str:
        return f"<EmailImport {self.email_type}: {self.subject}>"


class StatusHistory(Base):
    """Track status changes for applications."""

    __tablename__ = "status_history"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Multi-tenant
    application_id = Column(String, ForeignKey("applications.id"), nullable=False)
    old_status = Column(String)
    new_status = Column(String, nullable=False)
    changed_at = Column(DateTime, default=utcnow)
    notes = Column(Text)
