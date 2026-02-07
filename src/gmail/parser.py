"""Email parser for job-related emails."""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .client import EmailMessage


class EmailType(Enum):
    """Type of job-related email."""

    CONFIRMATION = "confirmation"
    REJECTION = "rejection"
    INTERVIEW_INVITE = "interview_invite"
    OFFER = "offer"
    UNKNOWN = "unknown"


@dataclass
class ParsedEmail:
    """Parsed job email data."""

    email_type: EmailType
    company: Optional[str] = None
    position: Optional[str] = None
    confidence: float = 0.0
    interview_date: Optional[str] = None
    calendar_link: Optional[str] = None
    rejection_stage: Optional[str] = None
    raw_email: Optional[EmailMessage] = None


class EmailParser:
    """Parse job-related emails to extract structured data."""

    def __init__(self, user_email: Optional[str] = None):
        """
        Initialize email parser.

        Args:
            user_email: User's own email address. Emails from this address
                        are classified as UNKNOWN (self-sent filtering).
        """
        self.user_email = user_email.lower() if user_email else None

    # Patterns for email type detection
    CONFIRMATION_PATTERNS = [
        r"thank you for (applying|your application|your interest)",
        r"thanks for (applying|your application|your interest)",
        r"thanks for applying to",
        r"we appreciate (you|your) applying",
        r"thanks from\s+\w+",  # "Thanks from {Company}"
        r"application (received|submitted|confirmed)",
        r"we (have )?(received|got) your application",
        r"successfully (submitted|applied)",
        r"your application (has been|was) (received|submitted)",
        r"thank you for applying to",
        r"your application to .+ at ",  # LinkedIn style: "Your application to X at Company"
        r"your application was sent to",  # LinkedIn style: "Sam, your application was sent to {Company}"
    ]

    REJECTION_PATTERNS = [
        r"after careful (consideration|review)",
        r"decided to (move forward|pursue) (with )?(other|different) candidates",
        r"not (moving forward|proceeding|advancing)",
        r"position has been filled",
        r"unfortunately",
        r"we (will not|won't) be (moving forward|proceeding)",
        r"regret to inform",
        r"we've decided not to",
        r"other candidates (whose|who)",
    ]

    # Strong interview signals (definitely scheduling an interview)
    INTERVIEW_STRONG_SIGNALS = [
        # Scheduling links
        r"calendly\.com",
        r"calendar\.google\.com",
        r"chili\s*piper",
        r"goodtime\.io",
        r"schedule\.once",
        # Booking requests
        r"book\s*(a|your)\s*time",
        r"pick\s*a\s*time",
        r"select\s*a\s*time",
        r"choose\s*a\s*time",
        r"please\s*(schedule|book|select)",
        r"schedule\s*(a|an|your)\s*(call|interview|meeting|conversation)\s*with",
        # Confirmed interviews
        r"interview\s*(is\s*)?(scheduled|confirmed)\s*(for)?",
        r"looking forward to (speaking|meeting|chatting) with you on",
        r"confirmed for (monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"(we'd|we would|i'd|i would) like to (schedule|invite you to|move you forward)",
        r"would like to schedule.{0,20}(interview|call|meeting|conversation)",
        # Meeting requests
        r"(we'd|we would|i'd|i would) (like|love) to meet",
        r"(like|love) to meet with (our|the) team",
        # Next steps (when explicitly about hiring)
        r"next steps?.{0,10}(in |for )?(the |your )?(hiring|interview|recruitment)",
        # Subject line patterns (explicit interview mentions)
        r"interview request",
        r"interview invitation",
        r"phone screen",
        r"recruiter (call|screen|chat)",
        r"zoom interview",
        r"video interview",
        r"upcoming.{0,20}interview",
        r"\|\s*(phone|video|zoom|recruiter).{0,15}(screen|interview|call)",
    ]

    # Weak interview signals (might indicate interest, but not definitive)
    INTERVIEW_WEAK_SIGNALS = [
        r"(next|following) (steps?|rounds?|stages?)",
        r"move(d|ing)? (forward|to the next)",
        r"would (like|love) to (speak|talk|chat|meet)",
        r"meet with (our|the) (team|hiring manager)",
        r"phone (screen|interview)",
        r"video (call|interview)",
        r"introductory (call|chat|conversation)",
    ]

    # Negative signals (indicate this is NOT an interview invite)
    INTERVIEW_NEGATIVE_SIGNALS = [
        r"if (we|the team) (decide|choose|would like) to (move|proceed|continue)",
        r"if (we|they).{0,20}(reach out|contact|be in touch)",
        r"if (your|the) (qualifications|experience|background) (match|align)",
        r"should (we|the team) (wish|decide|choose) to",
        r"will (let you know|be in touch|reach out|contact)",
        r"your application (was|has been) (sent|submitted|received)",
        r"we (will|may) (review|consider)",
        r"thank you for (applying|your (interest|application))",
        r"after (careful |reviewing |we ).{0,30}(unfortunately|regret|not)",
    ]

    OFFER_PATTERNS = [
        r"(pleased|excited|happy) to (offer|extend)",
        r"offer (letter|of employment)",
        r"extend (an |a )?offer",
        r"join (our|the) team",
        r"welcome (to|aboard)",
    ]

    # Subject-based company extraction patterns (most reliable)
    SUBJECT_COMPANY_PATTERNS = [
        # "Thanks for applying to {Company}" or "Thanks for applying to {Company}!"
        r"thanks for applying to\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*[!]?\s*$|\s*[-–])",
        # "Thanks from {Company}"
        r"thanks from\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Thank you from {Company}"
        r"thank you from\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "We Appreciate You Applying to {Company}"
        r"we appreciate (?:you|your) applying to\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Thank You for Applying to Join {Company}"
        r"thank you for applying to join\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*[!]?\s*$|\s*[-–])",
        # "Update from {Company}"
        r"update from\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Employment Update - {Company Name, LLC}" (Workday/ATS-style)
        r"employment update\s*[-–]\s*(.+?)(?:,\s*(?:LLC|Inc|Corp)\.?)?$",
        # "An update on your {Company} application"
        r"update on your\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)\s+application",
        # "{Company} Follow Up" / "{Company} Follow-Up"
        r"^([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)\s+follow[- ]?up",
        # "{Company} Update" or "{Company} Application" (exclude generic starts)
        r"^(?!(?:update|employment|an|the|a|your)\s)([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)\s+(?:update|application)(?:\s*$|\s*[-–])",
        # "Thank you for applying to {Company}"
        r"thank you for (?:applying|your interest|your application) (?:to|in|at)\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Thank you for your interest in joining {Company}"
        r"thank you for your interest in joining\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Thank you for your interest in {Company}"
        r"thank you for your interest in\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–]|\s*holding)",
        # "Update on your application with {Company}"
        r"(?:update on|regarding) your application (?:with|at|to)\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Your application for {role} at {Company}"
        r"your application (?:for|to).*?\s+at\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Your application to {Role} at {Company}"
        r"your application to .+? at\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Update on position at {Company}"
        r"update on (?:the )?position at\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–])",
        # "Follow-up from {Company}" (rejections often use this)
        r"follow-?up from\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*[-–|\|])",
        # "{Role} - {Company}" pattern (common in confirmation subjects)
        r"^(?:senior |lead |staff |principal )?(?:product manager|pm|engineer|developer)[^\|]+[-–]\s*([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$)",
        # "Sam, your application was sent to {Company}" (LinkedIn style)
        r"your application was sent to\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*$|\s*\.)",
        # "We have received your application for {Company}!"
        r"(?:we have )?received your application (?:for|to)\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*[!]?\s*$)",
        # "Application to {Company} successfully submitted"
        r"application to\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)\s+successfully",
        # "Thanks for your interest in {Company}"
        r"thanks for your interest in\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)(?:\s*[,!]|\s*$)",
        # "Following up on your {Company} ... Application"
        r"following up on your\s+([A-Za-z0-9][A-Za-z0-9\s&\.\-]+?)\s+(?:senior |lead |staff )?(?:product|application)",
    ]

    # Body-based company extraction patterns (fallback)
    BODY_COMPANY_PATTERNS = [
        r"(?:at|from|with)\s+([A-Z][A-Za-z0-9\s&]+?)(?:\.|,|\s+(?:and|is|has|we))",
        r"([A-Z][A-Za-z0-9\s&]+?)\s+(?:is|would like|team)",
        r"the\s+([A-Z][A-Za-z0-9\s&]+?)\s+team",
    ]

    # ATS domains that should NOT be used for company name extraction
    ATS_DOMAINS = {
        "greenhouse.io",
        "greenhouse-mail.io",
        "lever.co",
        "hire.lever.co",
        "workday.com",
        "myworkday.com",
        "icims.com",
        "talent.icims.com",
        "jobvite.com",
        "smartrecruiters.com",
        "ashbyhq.com",
        "rippling.com",
        "gem.com",
        "recruiting.experian.com",  # Subdomain ATS
        "workablemail.com",
        "candidates.workablemail.com",
        "candidatecare.io",
        "linkedin.com",
        "jobs-noreply@linkedin.com",
        "applytojob.com",
        "myworkdayjobs.com",
        "breezy.hr",
        "recruitee.com",
        "bamboohr.com",
        "jazz.co",
        "jazzhr.com",
        "paylocity.com",
        "paycom.com",
        "ceridian.com",
        "adp.com",
        "ultipro.com",
        "namely.com",
        "personio.com",
        "teamtailor.com",
        "recruitics.com",
        "fountain.com",
        "dover.io",
        "candidatecare.com",
    }

    # Subjects that indicate this is NOT a job application email
    EXCLUSION_PATTERNS = [
        r"referral request",
        r"referral for",
        r"networking request",
    ]

    def parse(self, email: EmailMessage) -> ParsedEmail:
        """
        Parse an email to extract job-related data.

        Args:
            email: Email message to parse

        Returns:
            ParsedEmail with extracted data
        """
        # Self-sent email filtering
        if self.user_email and email.from_address.lower() == self.user_email:
            return ParsedEmail(email_type=EmailType.UNKNOWN, confidence=0.0)

        # Combine subject and body for analysis
        text = f"{email.subject}\n{email.body_text}".lower()

        # Detect email type
        email_type, confidence = self._detect_type(text)

        # Extract company
        company = self._extract_company(email)

        # Extract position
        position = self._extract_position(email)

        result = ParsedEmail(
            email_type=email_type,
            company=company,
            position=position,
            confidence=confidence,
            raw_email=email,
        )

        # Type-specific extraction
        if email_type == EmailType.INTERVIEW_INVITE:
            result.calendar_link = self._extract_calendar_link(email)
            result.interview_date = self._extract_interview_date(email)

        if email_type == EmailType.REJECTION:
            result.rejection_stage = self._detect_rejection_stage(text)

        return result

    def _detect_type(self, text: str) -> tuple[EmailType, float]:
        """Detect the type of email and confidence score."""
        scores = {
            EmailType.CONFIRMATION: 0,
            EmailType.REJECTION: 0,
            EmailType.INTERVIEW_INVITE: 0,
            EmailType.OFFER: 0,
        }

        # Count pattern matches for confirmation
        for pattern in self.CONFIRMATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                scores[EmailType.CONFIRMATION] += 1

        # Count pattern matches for rejection
        for pattern in self.REJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                scores[EmailType.REJECTION] += 1

        # Count pattern matches for offer
        for pattern in self.OFFER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                scores[EmailType.OFFER] += 1

        # Interview detection uses weighted scoring
        interview_score = 0
        has_strong_signal = False

        # Strong signals are worth 3 points each
        for pattern in self.INTERVIEW_STRONG_SIGNALS:
            if re.search(pattern, text, re.IGNORECASE):
                interview_score += 3
                has_strong_signal = True

        # Weak signals are worth 1 point each
        for pattern in self.INTERVIEW_WEAK_SIGNALS:
            if re.search(pattern, text, re.IGNORECASE):
                interview_score += 1

        # Negative signals subtract 2 points each
        for pattern in self.INTERVIEW_NEGATIVE_SIGNALS:
            if re.search(pattern, text, re.IGNORECASE):
                interview_score -= 2

        # Only count as interview invite if:
        # - Has at least one strong signal, OR
        # - Has score >= 3 (multiple weak signals without negatives)
        if has_strong_signal or interview_score >= 3:
            scores[EmailType.INTERVIEW_INVITE] = max(0, interview_score)

        # Check exclusion patterns — override to UNKNOWN
        for pattern in self.EXCLUSION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return EmailType.UNKNOWN, 0.0

        # Find highest scoring type
        if max(scores.values()) == 0:
            return EmailType.UNKNOWN, 0.0

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # Calculate confidence
        if best_type == EmailType.INTERVIEW_INVITE:
            # For interviews, confidence based on signal strength
            confidence = min(1.0, best_score / 6.0)
        else:
            # For other types, normalize by pattern count
            pattern_counts = {
                EmailType.CONFIRMATION: len(self.CONFIRMATION_PATTERNS),
                EmailType.REJECTION: len(self.REJECTION_PATTERNS),
                EmailType.OFFER: len(self.OFFER_PATTERNS),
            }
            confidence = min(1.0, best_score / (pattern_counts.get(best_type, 1) * 0.3))

        return best_type, confidence

    def _extract_company(self, email: EmailMessage) -> Optional[str]:
        """Extract company name from email."""
        # Normalize subject — strip trailing punctuation that breaks $ anchors
        subject = re.sub(r"[!.]+\s*$", "", email.subject)

        # Step 1: Try subject-based patterns first (most reliable)
        for pattern in self.SUBJECT_COMPANY_PATTERNS:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                # Clean up and validate
                company = self._clean_company_name(company)
                if company and len(company) >= 2:
                    return company

        # Step 2: Check sender domain (but not for ATS platforms)
        from_domain = email.from_address.split("@")[-1] if "@" in email.from_address else ""
        is_ats = any(ats in from_domain for ats in self.ATS_DOMAINS)

        if not is_ats and from_domain:
            # Extract company from domain
            domain_parts = from_domain.split(".")
            company = domain_parts[0]
            # Skip common email providers
            if company.lower() not in ["gmail", "yahoo", "outlook", "hotmail", "mail", "email", "noreply", "no-reply"]:
                return company.title()
        elif is_ats:
            # For ATS domains, try extracting company from sender local part
            # e.g. "Aristocrat@myworkday.com" -> "Aristocrat"
            local_part = email.from_address.split("@")[0] if "@" in email.from_address else ""
            generic_locals = {
                "noreply", "no-reply", "donotreply", "do-not-reply",
                "recruiting", "talent", "hr", "jobs", "careers",
                "hiring", "notifications", "alerts", "info", "support",
            }
            if local_part and local_part.lower() not in generic_locals and len(local_part) >= 3:
                # Check it looks like a company name (starts with letter, not an email-like pattern)
                if local_part[0].isalpha() and "." not in local_part:
                    return local_part.title()

        # Step 3: Try body-based patterns (fallback)
        for pattern in self.BODY_COMPANY_PATTERNS:
            match = re.search(pattern, email.body_text[:500])
            if match:
                company = self._clean_company_name(match.group(1).strip())
                if company and len(company) >= 2:
                    return company

        # Step 4: Use sender name if nothing else works
        if email.from_name:
            # Clean up sender name (remove "via X", "at X", etc.)
            name = re.sub(r"\s+(?:via|at|from)\s+.*$", "", email.from_name, flags=re.IGNORECASE)
            name = self._clean_company_name(name)
            if name and len(name) >= 2:
                return name

        return None

    def _clean_company_name(self, name: str) -> Optional[str]:
        """Clean and validate a company name."""
        if not name:
            return None

        # Strip trailing punctuation (!, ., ,) that leaks from email subjects
        name = re.sub(r"[!.,;:]+$", "", name)

        # Remove common suffixes/prefixes
        name = re.sub(r"^(?:the|team|at|from|with|joining)\s+", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\s+(?:team|inc|llc|corp|ltd)\.?$", "", name, flags=re.IGNORECASE)

        # Remove extra whitespace
        name = " ".join(name.split())

        # Skip if it looks like a generic word or is too short
        generic_words = {
            "hi", "hello", "dear", "sam", "thanks", "thank", "you", "your",
            "update", "application", "joining", "employment", "an", "the",
            "follow", "follow-up", "followup",
        }
        if name.lower() in generic_words:
            return None

        # Reject names that are too long (likely sentence fragments)
        if len(name) > 50:
            return None

        # Reject names that look like sentences (contain common email verbs)
        sentence_indicators = [
            "thank you", "working here", "our exceptional", "we appreciate",
            "submitting your", "means you", "help chang", "connect with",
        ]
        name_lower = name.lower()
        if any(ind in name_lower for ind in sentence_indicators):
            return None

        return name if len(name) >= 2 else None

    def _extract_position(self, email: EmailMessage) -> Optional[str]:
        """Extract job position from email."""
        text = email.subject + "\n" + email.body_text[:1000]

        # Common patterns for position mentions
        position_patterns = [
            r"(?:for the|for our|applied for|application for)\s+([^.]+?)\s+(?:position|role|opening)",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:position|role|opening)",
            r"(?:position|role):\s*([^\n]+)",
        ]

        for pattern in position_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                position = match.group(1).strip()
                position = self._clean_position(position)
                if position:
                    return position

        return None

    def _clean_position(self, position: str) -> Optional[str]:
        """Clean and validate an extracted position string."""
        if not position:
            return None

        # Normalize whitespace
        position = re.sub(r"\s+", " ", position).strip()

        # Strip leading "the" (e.g., "the Staff Product Manager, AI" → "Staff Product Manager, AI")
        position = re.sub(r"^the\s+", "", position, flags=re.IGNORECASE)

        # Strip trailing punctuation
        position = re.sub(r"[!.,;:]+$", "", position).strip()

        # Reject strings that look like email phrases, not positions
        reject_starts = [
            "thank you", "thanks for", "we received", "your application",
            "submitting your", "we appreciate",
        ]
        pos_lower = position.lower()
        if any(pos_lower.startswith(phrase) for phrase in reject_starts):
            return None

        # Reasonable length check
        if len(position) < 3 or len(position) > 100:
            return None

        return position

    def _extract_calendar_link(self, email: EmailMessage) -> Optional[str]:
        """Extract calendar/scheduling link from email."""
        text = email.body_text + (email.body_html or "")

        # Common scheduling URLs
        patterns = [
            r"https?://calendly\.com/[^\s\"'<>]+",
            r"https?://calendar\.google\.com/[^\s\"'<>]+",
            r"https?://[^\s\"'<>]*schedule[^\s\"'<>]+",
            r"https?://[^\s\"'<>]*booking[^\s\"'<>]+",
            r"https?://outlook\.office365\.com/[^\s\"'<>]+",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)

        return None

    def _extract_interview_date(self, email: EmailMessage) -> Optional[str]:
        """Extract interview date/time from email."""
        text = email.body_text

        # Date patterns
        date_patterns = [
            r"(?:on|for)\s+([A-Z][a-z]+day,?\s+[A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)",
            r"(\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?)",
            r"([A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\s+at\s+(\d{1,2}:\d{2})",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)

        return None

    def _detect_rejection_stage(self, text: str) -> Optional[str]:
        """Detect at which stage the rejection occurred."""
        stage_indicators = {
            "resume": [
                r"resume review",
                r"initial (review|screening)",
                r"after reviewing (your|the) (application|resume)",
            ],
            "phone_screen": [
                r"phone (screen|interview|call)",
                r"initial (call|conversation)",
            ],
            "interview": [
                r"after (the |your )interview",
                r"following (the |your )interview",
                r"onsite",
                r"technical interview",
            ],
            "final_round": [
                r"final round",
                r"final interview",
                r"after much (deliberation|consideration)",
            ],
        }

        for stage, patterns in stage_indicators.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return stage

        return None

    # Map ATS/platform domains to source names for analytics
    SOURCE_DOMAIN_MAP = {
        "linkedin.com": "linkedin",
        "jobs-noreply@linkedin.com": "linkedin",
        "greenhouse.io": "greenhouse",
        "greenhouse-mail.io": "greenhouse",
        "lever.co": "lever",
        "hire.lever.co": "lever",
        "ashbyhq.com": "ashby",
        "workday.com": "workday",
        "myworkday.com": "workday",
        "myworkdayjobs.com": "workday",
        "smartrecruiters.com": "smartrecruiters",
        "indeed.com": "indeed",
        "glassdoor.com": "glassdoor",
        "icims.com": "icims",
        "talent.icims.com": "icims",
        "hi.wellfound.com": "wellfound",
        "wellfound.com": "wellfound",
        "jobvite.com": "jobvite",
        "rippling.com": "rippling",
        "ats.rippling.com": "rippling",
        "workablemail.com": "workable",
        "candidates.workablemail.com": "workable",
        "breezy.hr": "breezy",
        "bamboohr.com": "bamboohr",
        "teamtailor.com": "teamtailor",
        "dover.io": "dover",
        "gem.com": "gem",
        "appreview.gem.com": "gem",
    }

    @classmethod
    def infer_source(cls, from_address: str) -> str:
        """Infer application source from email sender address.

        Returns a specific source name (e.g., 'linkedin', 'greenhouse')
        instead of the generic 'email_import'.
        """
        if not from_address:
            return "email_import"

        from_lower = from_address.lower()
        domain = from_lower.split("@")[-1] if "@" in from_lower else ""

        # Check full address first (e.g., jobs-noreply@linkedin.com)
        if from_lower in cls.SOURCE_DOMAIN_MAP:
            return cls.SOURCE_DOMAIN_MAP[from_lower]

        # Check domain and subdomains
        for pattern_domain, source in cls.SOURCE_DOMAIN_MAP.items():
            if domain == pattern_domain or domain.endswith("." + pattern_domain):
                return source

        # If it's a company domain (not ATS), keep as email_import
        return "email_import"

    def is_job_related(self, email: EmailMessage) -> bool:
        """Quick check if email is likely job-related."""
        indicators = [
            "application",
            "applying",
            "position",
            "role",
            "opportunity",
            "candidate",
            "hiring",
            "interview",
            "resume",
            "job",
            "career",
            "recruitment",
            "talent",
            "offer",
        ]

        text = f"{email.subject} {email.snippet}".lower()
        return any(ind in text for ind in indicators)
