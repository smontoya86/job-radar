# Job Radar System Architecture

## Overview

Job Radar is a two-part system designed to automate job discovery and application tracking:

1. **Job Radar** - Continuous background monitoring of job boards with intelligent matching
2. **Application Tracker** - Full lifecycle tracking from application to offer/rejection

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              JOB RADAR SYSTEM                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  COLLECTORS │───▶│   MATCHER   │───▶│    DEDUP    │───▶│  NOTIFIER   │  │
│  │             │    │   & SCORER  │    │             │    │             │  │
│  │ • JobSpy    │    │             │    │ Fingerprint │    │   Slack     │  │
│  │ • RemoteOK  │    │ • Keywords  │    │   based     │    │  Webhook    │  │
│  │ • Greenhouse│    │ • Title     │    │ dedup with  │    │             │  │
│  │ • Lever     │    │ • Company   │    │  30-day     │    │ Rich cards  │  │
│  │ • HN        │    │ • Salary    │    │  lookback   │    │ with score  │  │
│  │ • Adzuna    │    │ • Remote    │    │             │    │             │  │
│  │ • Wellfound │    │             │    │             │    │             │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│         │                  │                  │                  │         │
│         ▼                  ▼                  ▼                  ▼         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         SQLite DATABASE                             │   │
│  │  ┌─────────┐  ┌──────────────┐  ┌─────────┐  ┌────────────────┐    │   │
│  │  │  Jobs   │  │ Applications │  │ Resumes │  │ Email Imports  │    │   │
│  │  └─────────┘  └──────────────┘  └─────────┘  └────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                         │                              ▲                   │
├─────────────────────────┼──────────────────────────────┼───────────────────┤
│                         │    APPLICATION TRACKER       │                   │
├─────────────────────────┼──────────────────────────────┼───────────────────┤
│                         ▼                              │                   │
│  ┌─────────────────────────────────────────────────────┼───────────────┐   │
│  │                    STREAMLIT DASHBOARD              │               │   │
│  │  ┌─────────┐  ┌──────────────┐  ┌──────────┐  ┌────┴─────┐        │   │
│  │  │  Jobs   │  │ Applications │  │ Pipeline │  │ Analytics │        │   │
│  │  │  Page   │  │    Page      │  │  Board   │  │   Page    │        │   │
│  │  └─────────┘  └──────────────┘  └──────────┘  └──────────┘        │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                        ▲                   │
│  ┌─────────────────────────────────────────────────────┴───────────────┐   │
│  │                      GMAIL INTEGRATION                              │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │   │
│  │  │   OAuth2    │───▶│  Fetcher    │───▶│   Parser                │ │   │
│  │  │   Auth      │    │             │    │   • Confirmations       │ │   │
│  │  └─────────────┘    │ Search for  │    │   • Rejections          │ │   │
│  │                     │ job emails  │    │   • Interview invites   │ │   │
│  │                     └─────────────┘    └─────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
job-radar/
├── config/
│   ├── settings.py          # Pydantic settings (env vars)
│   └── profile.yaml         # Job search criteria
│
├── src/
│   ├── main.py              # Scheduler entry point
│   │
│   ├── collectors/          # Job source modules
│   │   ├── base.py          # BaseCollector, JobData dataclass
│   │   ├── utils.py         # Shared utilities (parse_salary, parse_date, etc.)
│   │   ├── jobspy_collector.py
│   │   ├── remoteok_collector.py
│   │   ├── adzuna_collector.py
│   │   ├── greenhouse_collector.py
│   │   ├── lever_collector.py
│   │   ├── hn_collector.py
│   │   └── wellfound_collector.py
│   │
│   ├── matching/
│   │   ├── keyword_matcher.py  # Description-centric scoring (v2)
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
│   │   ├── database.py         # Session management
│   │   └── cleanup.py          # Data retention (60-day cleanup)
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
│   ├── common.py               # Shared initialization
│   └── pages/
│       ├── 1_jobs.py           # New job matches
│       ├── 2_applications.py   # Application tracker
│       ├── 3_pipeline.py       # Kanban board
│       ├── 4_analytics.py      # Charts
│       └── 5_rejection_analysis.py
│
├── scripts/
│   ├── bootstrap.py            # Shared path setup
│   ├── run_scan.py             # One-time scan (for CI)
│   ├── setup_gmail.py          # Gmail OAuth setup
│   ├── setup_slack.py          # Test Slack webhook
│   └── reprocess_emails.py     # Re-parse emails
│
├── launchd/
│   └── com.jobradar.plist.example
│
├── data/                       # Docker database volume
├── logs/
└── tests/
```

---

## Component Deep Dive

### 1. Job Collectors (`src/collectors/`)

Each collector implements the `BaseCollector` interface:

```python
class BaseCollector(ABC):
    name: str  # Unique identifier for this source

    @abstractmethod
    async def collect(self, search_queries: list[str]) -> list[JobData]:
        pass
```

| Collector | Source | Method | Notes |
|-----------|--------|--------|-------|
| `JobSpyCollector` | Indeed, LinkedIn, Glassdoor, Google | python-jobspy | Primary source |
| `RemoteOKCollector` | remoteok.com | Public API | Remote-only jobs |
| `GreenhouseCollector` | Greenhouse boards | Public API | 20+ tech companies |
| `LeverCollector` | Lever boards | Public API | 20+ startups |
| `HNCollector` | Hacker News | Algolia API | Monthly "Who's Hiring" |
| `AdzunaCollector` | Adzuna | API (key required) | Optional |
| `WellfoundCollector` | Wellfound/AngelList | Web scraping | Startup jobs |

**JobData Schema:**
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

**Collector-Specific Notes:**

- **Greenhouse**: List endpoint does NOT include descriptions. Must fetch each job individually. Returns HTML-encoded content - decode with `html.unescape()` before BeautifulSoup.
- **Lever**: Returns full job data including description. May include HTML - strip with BeautifulSoup.
- **HN**: Scrapes monthly "Who is hiring?" threads via HN Algolia API.

---

### 2. Matching Algorithm (Description-Centric v2)

Located in `src/matching/keyword_matcher.py`

**Philosophy:** Job titles can be misleading. A "Staff Product Manager" with an AI/ML-heavy description is more relevant than an "AI Product Manager" with a generic description.

**Scoring Weights:**

| Component | Weight | Description |
|-----------|--------|-------------|
| Description Keywords | 40% | Primary focus - keywords in job description |
| Title Relevance | 20% | Exact match or partial credit for related titles |
| Keyword Variety | 15% | More unique keywords = more relevant |
| Company Tier | 15% | Tier 1 (100%), Tier 2 (70%), Tier 3 (40%) |
| Salary/Remote | 10% | 5% each for matching preferences |

**Match Criteria:** A job matches if ANY of these are true:
1. Primary keywords found in description
2. Primary keywords found in title
3. Exact title match from target_titles
4. Company is in target_companies list

**Score Thresholds:**
- 80+ = Excellent Match
- 60-79 = Good Match
- 30-59 = Potential Match
- <30 = Not saved

---

### 3. Deduplication (`src/dedup/`)

Prevents seeing the same job multiple times:

```
Job → Generate Fingerprint → Check Database → New? → Save

fingerprint = normalize(company) + ":" + normalize(title)
Example: "stripe:senior ai product manager"
```

- 30-day lookback window
- Fingerprints stored in SQLite
- Batch dedup within same scan

---

### 4. Database Schema

```
┌─────────────────┐     ┌─────────────────┐
│      Jobs       │     │    Resumes      │
├─────────────────┤     ├─────────────────┤
│ id (PK)         │     │ id (PK)         │
│ title           │     │ name            │
│ company         │     │ version         │
│ location        │     │ file_path       │
│ description     │     │ target_roles    │
│ salary_min/max  │     │ is_active       │
│ url             │     └────────┬────────┘
│ source          │              │
│ remote          │              │
│ match_score     │              │
│ fingerprint     │              │
│ status          │              │
└────────┬────────┘              │
         │                       │
         │    ┌──────────────────┴──────────────────┐
         │    │           Applications              │
         │    ├─────────────────────────────────────┤
         └───▶│ id (PK)                             │
              │ job_id (FK)                         │
              │ resume_id (FK)                      │
              │ company, position                   │
              │ applied_date, status                │
              │ interview_rounds                    │
              │ rejected_at, offer_amount           │
              └────────┬────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌─────────────────┐     ┌─────────────────┐
│   Interviews    │     │  EmailImports   │
├─────────────────┤     ├─────────────────┤
│ application_id  │     │ gmail_message_id│
│ round, type     │     │ subject         │
│ scheduled_at    │     │ email_type      │
│ outcome         │     │ application_id  │
└─────────────────┘     └─────────────────┘
```

**Application Status Flow:**
```
applied ──▶ phone_screen ──▶ interviewing ──▶ offer ──▶ accepted
   │              │               │            │
   └──────────────┴───────────────┴────────────┴──▶ rejected
   │
   └──▶ ghosted (no response 2+ weeks)
   └──▶ withdrawn
```

---

### 5. Gmail Integration

**Authentication Flow:**
```
credentials.json → OAuth2 Flow → token.json → API Access
```

**Email Classification:**

| Type | Detection Patterns |
|------|-------------------|
| Confirmation | "thank you for applying", "application received" |
| Rejection | "after careful consideration", "decided to move forward" |
| Interview | "schedule an interview", calendly.com links |
| Offer | "pleased to offer", "extend an offer" |

---

## Deployment Options

### Option 1: Docker (Recommended)

```bash
./docker-start.sh   # Start dashboard + scanner
./docker-stop.sh    # Stop everything

# Or manually:
docker compose up -d
docker compose logs -f
docker compose down
```

**Services:**
- `dashboard` - Streamlit UI at http://localhost:8501
- `scanner` - Background job radar

**Data:** Persisted in `./data/job_radar.db`

### Option 2: Local with launchd (macOS)

```bash
# Copy plist to LaunchAgents
cp launchd/com.jobradar.plist.example ~/Library/LaunchAgents/com.jobradar.plist
# Edit paths in plist

# Load/start
launchctl load ~/Library/LaunchAgents/com.jobradar.plist

# Unload/stop
launchctl unload ~/Library/LaunchAgents/com.jobradar.plist
```

### Option 3: GitHub Actions (Cloud)

Runs scanner every 30 minutes with Supabase PostgreSQL. See `.github/workflows/job-scan.yml`.

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Language | Python 3.12 | Core runtime |
| Web Framework | Streamlit | Dashboard UI |
| Database | SQLite + SQLAlchemy | Persistence |
| Scheduler | APScheduler | Background jobs |
| HTTP Client | aiohttp | Async API calls |
| Job Scraping | python-jobspy | LinkedIn/Indeed/etc |
| Charts | Plotly | Analytics |
| Notifications | Slack SDK | Webhook messages |
| Email | Google API | Gmail integration |
| Config | Pydantic | Settings validation |
| Containers | Docker Compose | Deployment |

---

## Configuration

### profile.yaml

```yaml
target_titles:
  primary:
    - "AI Product Manager"
    - "Senior AI Product Manager"
  secondary:
    - "Product Manager, AI"

required_keywords:
  primary:   # Must match at least one
    - "AI"
    - "ML"
    - "search"
    - "GenAI"
  secondary: # Bonus points
    - "product manager"
    - "agentic"

negative_keywords:  # Auto-reject
  - "junior"
  - "intern"

target_companies:
  tier1: ["OpenAI", "Anthropic", "Google"]
  tier2: ["Stripe", "Airbnb", "Figma"]
  tier3: ["Spotify", "Pinterest"]

compensation:
  min_salary: 185000
  max_salary: 225000
```

### .env

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json
DATABASE_URL=sqlite:///job_radar.db
```

---

## Security

1. **Credentials** - `.env`, `credentials.json`, `token.json` excluded from git
2. **Rate Limiting** - Collectors have built-in delays, scheduler prevents overlapping runs
3. **Data Privacy** - All data stored locally, no external sharing, Gmail read-only access
