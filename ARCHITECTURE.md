# Job Radar - System Architecture

## Overview

Job Radar is a complete job search automation system with two integrated components:

1. **Job Radar** - Background service that monitors job boards, scores matches, sends Slack alerts
2. **Application Tracker** - Web dashboard for tracking applications, resumes, interviews, analytics

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         JOB RADAR SYSTEM                            │
├─────────────────────────────────────────────────────────────────────┤
│  COLLECTORS          MATCHER           NOTIFICATIONS                │
│  ┌─────────┐        ┌────────┐        ┌────────────┐               │
│  │ Indeed  │───────▶│Keyword │───────▶│   Slack    │               │
│  │ RemoteOK│        │Scoring │        │  Webhook   │               │
│  │ Adzuna  │        │ + Dedup│        └────────────┘               │
│  │Greenhouse│        └────────┘                                     │
│  │ Lever   │             │                                          │
│  │   HN    │             ▼                                          │
│  └─────────┘        ┌────────┐                                      │
│                     │ SQLite │◀─────────────────────┐               │
│                     │   DB   │                      │               │
│                     └────────┘                      │               │
├─────────────────────────────────────────────────────────────────────┤
│                    APPLICATION TRACKER                              │
├─────────────────────────────────────────────────────────────────────┤
│  GMAIL IMPORT       TRACKING           WEB DASHBOARD                │
│  ┌─────────┐        ┌────────┐        ┌────────────────────────┐   │
│  │ Gmail   │───────▶│ Parse  │───────▶│  Applications Table    │   │
│  │   API   │        │ Emails │        │  Pipeline Board        │   │
│  └─────────┘        │(confirm,│        │  Resume Versions       │   │
│                     │ reject) │        │  Analytics Charts      │   │
│       │             └────────┘        └────────────────────────┘   │
│       │                  │                      ▲                   │
│       └──────────────────┴──────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
job-radar/
├── config/
│   ├── settings.py          # Pydantic settings (env vars)
│   └── profile.yaml         # Job search criteria
│
├── src/
│   ├── main.py              # Scheduler entry point (launchd runs this)
│   │
│   ├── collectors/          # Job source modules
│   │   ├── base.py          # BaseCollector, JobData dataclass
│   │   ├── jobspy_collector.py
│   │   ├── remoteok_collector.py
│   │   ├── adzuna_collector.py
│   │   ├── greenhouse_collector.py
│   │   ├── lever_collector.py
│   │   ├── hn_collector.py
│   │   └── wellfound_collector.py
│   │
│   ├── matching/
│   │   ├── keyword_matcher.py  # Description-centric scoring
│   │   └── scorer.py           # Orchestrates matching + dedup
│   │
│   ├── dedup/
│   │   └── deduplicator.py     # Fingerprint-based deduplication
│   │
│   ├── notifications/
│   │   └── slack_notifier.py
│   │
│   ├── persistence/
│   │   ├── models.py           # SQLAlchemy models
│   │   └── database.py         # Session management
│   │
│   ├── gmail/
│   │   ├── auth.py             # OAuth2 setup
│   │   ├── client.py           # Gmail API wrapper
│   │   └── parser.py           # Parse application emails
│   │
│   ├── tracking/
│   │   ├── application_service.py
│   │   └── resume_service.py
│   │
│   └── analytics/
│       ├── funnel.py
│       ├── source_analysis.py
│       └── resume_analysis.py
│
├── dashboard/
│   ├── app.py                  # Streamlit entry point
│   └── pages/
│       ├── 1_jobs.py           # New job matches
│       ├── 2_applications.py   # Application tracker
│       ├── 3_pipeline.py       # Kanban board
│       └── 4_analytics.py      # Charts
│
├── launchd/
│   └── com.sammontoya.jobradar.plist  # Background service config
│
├── logs/
│   └── jobradar.log            # Service logs
│
└── tests/
    ├── test_matching.py
    └── ...
```

## Collector Architecture

All collectors inherit from `BaseCollector`:

```python
class BaseCollector(ABC):
    name: str  # Unique identifier for this source

    @abstractmethod
    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """Fetch jobs matching search queries."""
        pass
```

### JobData Schema

```python
@dataclass
class JobData:
    title: str
    company: str
    url: str
    source: str
    location: Optional[str] = None
    description: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    apply_url: Optional[str] = None
    remote: bool = False
    posted_date: Optional[datetime] = None
    extra_data: dict = field(default_factory=dict)
```

### Collector-Specific Notes

**Greenhouse** (`greenhouse_collector.py`):
- Uses boards-api.greenhouse.io
- List endpoint does NOT include descriptions
- Must fetch each job individually for description
- Returns HTML-encoded content - decode with `html.unescape()` before BeautifulSoup
- Store job_id in extra_data for description fetch

**Lever** (`lever_collector.py`):
- Uses api.lever.co/v0/postings/{company}
- Returns full job data including description
- May include HTML in description - strip with BeautifulSoup

**HN Who's Hiring** (`hn_collector.py`):
- Scrapes monthly "Who is hiring?" threads
- Uses HN Algolia API

## Matching Algorithm (Description-Centric v2)

Located in `src/matching/keyword_matcher.py`

### Philosophy

The key insight: Job titles can be misleading. A "Staff Product Manager" with an AI/ML-heavy description is more relevant than an "AI Product Manager" with a generic description.

### Scoring Weights

| Component | Weight | Description |
|-----------|--------|-------------|
| Description Keywords | 40% | Primary focus - what keywords appear in job description |
| Title Relevance | 20% | Exact match or partial credit for related titles |
| Keyword Variety | 15% | More unique keywords = more relevant |
| Company Tier | 15% | Tier 1 (100%), Tier 2 (70%), Tier 3 (40%) |
| Salary/Remote | 10% | 5% each for matching preferences |

### Match Criteria

A job matches if ANY of these are true:
1. Primary keywords found in description
2. Primary keywords found in title
3. Exact title match from target_titles
4. Company is in target_companies list

### MatchResult Fields

```python
@dataclass
class MatchResult:
    matched: bool
    score: float  # 0-100
    matched_primary: list[str]
    matched_secondary: list[str]
    matched_title: bool
    matched_company_tier: Optional[int]
    negative_matches: list[str]
    salary_match: bool
    remote_match: bool
    description_keyword_count: int      # Total keyword mentions
    description_keyword_variety: int    # Unique keywords found
    title_partial_match: float          # 0-1 partial title score
```

## Database Schema

### Core Tables

**jobs** - Discovered jobs from collectors
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    description TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    url TEXT NOT NULL,
    apply_url TEXT,
    source TEXT NOT NULL,
    remote BOOLEAN,
    match_score REAL,
    matched_keywords JSON,
    fingerprint TEXT,
    posted_date DATETIME,
    discovered_at DATETIME,
    notified_at DATETIME,
    status TEXT DEFAULT 'new'
);
```

**applications** - Tracked applications
```sql
CREATE TABLE applications (
    id TEXT PRIMARY KEY,
    job_id TEXT REFERENCES jobs(id),
    company TEXT NOT NULL,
    position TEXT NOT NULL,
    applied_date DATE NOT NULL,
    source TEXT,
    resume_id TEXT REFERENCES resumes(id),
    cover_letter_used BOOLEAN,
    referral_name TEXT,
    status TEXT NOT NULL,
    current_stage TEXT,
    last_status_change DATETIME,
    interview_rounds INTEGER DEFAULT 0,
    next_interview_date DATETIME,
    interview_notes TEXT,
    rejected_at TEXT,
    rejection_reason TEXT,
    offer_amount INTEGER,
    offer_equity TEXT,
    notes TEXT,
    created_at DATETIME,
    updated_at DATETIME
);
```

**resumes** - Resume versions
```sql
CREATE TABLE resumes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    file_path TEXT,
    version INTEGER,
    target_roles TEXT,
    key_changes TEXT,
    created_at DATETIME,
    is_active BOOLEAN DEFAULT true
);
```

**interviews** - Interview tracking
```sql
CREATE TABLE interviews (
    id TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(id),
    round INTEGER,
    type TEXT,  -- Phone Screen, HM Interview, Product Sense, etc.
    scheduled_at DATETIME,
    interviewers TEXT,
    duration_minutes INTEGER,
    topics TEXT,
    outcome TEXT,
    feedback TEXT,
    notes TEXT
);
```

## Application Status Flow

```
applied ──▶ phone_screen ──▶ interviewing ──▶ offer ──▶ accepted
   │              │               │            │
   └──────────────┴───────────────┴────────────┴──▶ rejected
   │
   └──▶ ghosted (no response 2+ weeks)
   │
   └──▶ withdrawn
```

### Valid Statuses
- `applied` - Initial submission
- `phone_screen` - Recruiter screen
- `interviewing` - Active interview process
- `offer` - Received offer
- `accepted` - Accepted offer
- `rejected` - Rejected at any stage
- `withdrawn` - Self-withdrew
- `ghosted` - No response

### Interview Types
- Phone Screen
- HM Interview
- Product Sense
- Technical
- Behavioral
- Panel
- Onsite
- Take Home
- Final Round
- Other

## Background Service (launchd)

The system runs as a macOS LaunchAgent:

```xml
<!-- launchd/com.sammontoya.jobradar.plist -->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sammontoya.jobradar</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/sammontoya/job-hunt/job-radar/venv/bin/python</string>
        <string>-u</string>  <!-- Unbuffered output for logs -->
        <string>/Users/sammontoya/job-hunt/job-radar/src/main.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/sammontoya/job-hunt/job-radar/logs/jobradar.log</string>
</dict>
</plist>
```

### Key Points
- Uses `-u` flag for unbuffered Python output (otherwise logs don't appear)
- RunAtLoad starts service on login
- KeepAlive restarts if it crashes
- Uses venv Python directly (not system Python)

## Configuration

### profile.yaml

```yaml
target_titles:
  primary:
    - "AI Product Manager"
    - "Senior AI Product Manager"
    - "Staff Product Manager"
  secondary:
    - "Product Manager, AI"
    - "Product Manager, ML"

required_keywords:
  primary:  # Must match at least one
    - "AI"
    - "ML"
    - "machine learning"
    - "search"
    - "GenAI"
    - "LLM"
  secondary:  # Bonus points
    - "product manager"
    - "agentic"
    - "RAG"

negative_keywords:  # Auto-reject
  - "junior"
  - "intern"
  - "contractor"

target_companies:
  tier1: ["OpenAI", "Anthropic", "Google"]
  tier2: ["Stripe", "Airbnb", "Figma"]
  tier3: ["Spotify", "Pinterest", "Discord"]

compensation:
  min_salary: 185000
  max_salary: 225000
  flexible: true
```

### .env

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json
DATABASE_URL=sqlite:///job_radar.db
```

## Testing

```bash
# Run all tests
cd /Users/sammontoya/job-hunt/job-radar
source venv/bin/activate
pytest

# Run specific test file
pytest tests/test_matching.py -v

# Run with coverage
pytest --cov=src
```

### Key Test Classes
- `TestKeywordMatcher` - Profile loading, keyword matching
- `TestJobScorer` - Scoring, filtering, fingerprinting
- `TestDescriptionCentricScoring` - New algorithm tests
