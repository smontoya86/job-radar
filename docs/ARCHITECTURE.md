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
│  │ 14 sources: │    │             │    │ Fingerprint │    │   Slack     │  │
│  │ ATS boards  │    │ Description │    │   based     │    │  Webhook    │  │
│  │ Public APIs │    │  -centric   │    │ dedup with  │    │             │  │
│  │ Aggregators │    │  scoring    │    │  30-day     │    │ Rich cards  │  │
│  │ (see below) │    │             │    │  lookback   │    │ with score  │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│         │                  │                  │                  │         │
│         ▼                  ▼                  ▼                  ▼         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    DATABASE (PostgreSQL / SQLite)                    │   │
│  │  ┌──────┐ ┌──────────────┐ ┌────────┐ ┌──────────────┐ ┌────────┐ │   │
│  │  │ Jobs │ │ Applications │ │Resumes │ │ EmailImports │ │ Status │ │   │
│  │  │      │ │              │ │        │ │              │ │History │ │   │
│  │  └──────┘ └──────────────┘ └────────┘ └──────────────┘ └────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                         │                              ▲                   │
├─────────────────────────┼──────────────────────────────┼───────────────────┤
│                         │    APPLICATION TRACKER       │                   │
├─────────────────────────┼──────────────────────────────┼───────────────────┤
│                         ▼                              │                   │
│  ┌─────────────────────────────────────────────────────┼───────────────┐   │
│  │                    STREAMLIT DASHBOARD              │               │   │
│  │ ┌──────┐ ┌──────┐ ┌────────┐ ┌─────────┐ ┌───────┴──┐ ┌────────┐ │   │
│  │ │ Jobs │ │ Apps │ │Pipeline│ │Analytics│ │Rejection │ │Settings│ │   │
│  │ │      │ │      │ │ Board  │ │         │ │ Analysis │ │        │ │   │
│  │ └──────┘ └──────┘ └────────┘ └─────────┘ └──────────┘ └────────┘ │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                        ▲                   │
│  ┌─────────────────────────────────────────────────────┴───────────────┐   │
│  │                      GMAIL INTEGRATION                              │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │   │
│  │  │   OAuth2    │───▶│  Fetcher    │───▶│   Parser                │ │   │
│  │  │   Auth      │    │             │    │   • Confirmations       │ │   │
│  │  └─────────────┘    │ Search for  │    │   • Rejections          │ │   │
│  │                     │ job emails  │    │   • Interview invites   │ │   │
│  │                     └─────────────┘    │   • Offers              │ │   │
│  │                                        └─────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
job-radar/
├── config/
│   ├── settings.py            # Pydantic settings (env vars)
│   └── profile.yaml           # Job search criteria
│
├── src/
│   ├── main.py                # Scheduler entry point (APScheduler)
│   │
│   ├── collectors/            # Job source modules
│   │   ├── base.py            # BaseCollector, JobData dataclass
│   │   ├── utils.py           # Shared utilities (parse_salary, parse_date, etc.)
│   │   ├── remoteok_collector.py
│   │   ├── greenhouse_collector.py
│   │   ├── lever_collector.py
│   │   ├── ashby_collector.py
│   │   ├── workday_collector.py
│   │   ├── smartrecruiters_collector.py
│   │   ├── hn_collector.py
│   │   ├── adzuna_collector.py
│   │   ├── serpapi_collector.py
│   │   ├── jsearch_collector.py
│   │   ├── search_discovery_collector.py
│   │   ├── remotive_collector.py
│   │   ├── himalayas_collector.py
│   │   └── themuse_collector.py
│   │
│   ├── matching/
│   │   ├── keyword_matcher.py    # Description-centric scoring (v2)
│   │   ├── scorer.py             # JobScorer + get_scorer() factory
│   │   └── scorer_protocol.py    # Scorer protocol (AI-ready interface)
│   │
│   ├── pipeline/
│   │   └── enricher.py           # Enricher protocol + NoOpEnricher
│   │
│   ├── dedup/
│   │   └── deduplicator.py       # Fingerprint-based deduplication
│   │
│   ├── notifications/
│   │   └── slack_notifier.py
│   │
│   ├── persistence/
│   │   ├── models.py             # SQLAlchemy models (9 models)
│   │   ├── database.py           # Session management, init_db, auto-migration
│   │   └── cleanup.py            # Data retention (60-day cleanup)
│   │
│   ├── gmail/
│   │   ├── auth.py               # OAuth2 setup
│   │   ├── client.py             # Gmail API wrapper
│   │   └── parser.py             # Email classification & extraction
│   │
│   ├── tracking/
│   │   ├── application_service.py  # Application CRUD, _try_link_to_job
│   │   └── resume_service.py
│   │
│   ├── analytics/
│   │   ├── funnel.py              # Effective-stage funnel analytics
│   │   ├── source_analysis.py     # Source effectiveness
│   │   ├── rejection_analysis.py  # Skill gap analysis from rejections
│   │   └── resume_analysis.py     # Resume performance tracking
│   │
│   ├── onboarding/
│   │   ├── validators.py          # Pydantic validation models
│   │   ├── profile_builder.py     # Fluent builder for config
│   │   ├── config_writer.py       # Write profile.yaml and .env
│   │   └── config_checker.py      # is_configured() detection
│   │
│   └── auth/                      # Auth scaffold (not active)
│       ├── service.py             # AuthService (register, login, OAuth)
│       ├── exceptions.py          # Auth exception types
│       └── rate_limit.py          # In-memory rate limiter utility
│
├── dashboard/
│   ├── app.py                    # Streamlit entry point
│   ├── common.py                 # Shared init (path setup, init_db, sanitize_html)
│   ├── pages/
│   │   ├── 0_setup.py            # 9-step setup wizard
│   │   ├── 1_jobs.py             # Browse job matches
│   │   ├── 2_applications.py     # Application tracker + interviews + resumes
│   │   ├── 3_pipeline.py         # Kanban board
│   │   ├── 4_analytics.py        # Funnel, source, resume charts
│   │   ├── 5_rejection_analysis.py  # Skill gap analysis (cached)
│   │   └── 6_settings.py         # Edit profile from dashboard
│   └── components/
│       ├── charts.py             # Plotly chart helpers
│       └── job_card.py           # Job card UI component
│
├── scripts/
│   ├── bootstrap.py              # Shared path setup for scripts
│   ├── run_scan.py               # One-time scan (for CI)
│   ├── setup_gmail.py            # Gmail OAuth setup
│   ├── setup_slack.py            # Test Slack webhook
│   ├── reprocess_emails.py       # Re-parse existing emails
│   ├── import_historical.py      # Historical email import
│   ├── backfill_job_descriptions.py  # Backfill missing job descriptions
│   ├── backfill_interviews.py    # Backfill interview records
│   ├── migrate_statuses.py       # Status migration utility
│   ├── cleanup_orphaned_records.py
│   └── validate_before_migration.py
│
├── tests/
│   ├── conftest.py               # Fixtures (test_db, samples, mocks)
│   ├── test_gmail.py             # Email parser & classification
│   ├── test_onboarding.py        # Onboarding wizard (48 tests)
│   ├── test_matching.py          # Keyword matcher, scorer, protocol tests
│   ├── test_collectors.py        # Collector tests
│   ├── test_analytics.py         # Analytics tests
│   ├── test_services.py          # Service layer + _try_link_to_job tests
│   ├── test_models.py            # ORM model tests
│   ├── unit/
│   │   ├── test_auth_service.py  # Auth service tests
│   │   └── test_user_model.py    # User model tests
│   ├── security/
│   │   ├── test_data_isolation.py  # Multi-tenant isolation
│   │   └── test_sql_injection.py   # SQL injection + LIKE escaping
│   └── e2e/                      # End-to-end tests
│
├── docs/
│   ├── ARCHITECTURE.md           # This file
│   └── SETUP_GUIDE.md            # Slack & Gmail setup
│
├── launchd/
│   └── com.jobradar.plist.example
│
├── data/                         # SQLite database (local dev only)
└── logs/                         # Application logs
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

| Collector | Source | Type | API Key | Notes |
|-----------|--------|------|:---:|-------|
| `RemoteOKCollector` | remoteok.com | Public API | No | Remote-only jobs |
| `GreenhouseCollector` | Greenhouse boards | Public ATS | No | 130+ tech companies |
| `LeverCollector` | Lever boards | Public ATS | No | 75+ startups |
| `AshbyCollector` | Ashby boards | Public ATS | No | Growing startup ATS |
| `WorkdayCollector` | Workday career sites | Public ATS | No | Large enterprises |
| `SmartRecruitersCollector` | SmartRecruiters | Public ATS | No | Enterprise career sites |
| `HNCollector` | Hacker News | Public API | No | Monthly "Who's Hiring" |
| `RemotiveCollector` | Remotive | Public API | No | Remote job board |
| `HimalayasCollector` | Himalayas | Public API | No | Remote company profiles |
| `TheMuseCollector` | TheMuse | Public API | No | Company career content |
| `AdzunaCollector` | Adzuna | API | Yes | UK/US/AU aggregator |
| `SerpApiCollector` | Google Jobs via SerpApi | API | Yes | Aggregates Indeed, LinkedIn, Glassdoor |
| `JSearchCollector` | JSearch (RapidAPI) | API | Yes | Multi-source aggregator |
| `SearchDiscoveryCollector` | SerpApi `site:` queries | API | SerpApi key | Discovers new ATS boards |

All sources use public APIs or authorized data. JobSpy and Wellfound (high-risk scrapers) were removed and replaced with these compliant alternatives.

**Collector-Specific Notes:**

- **Greenhouse**: List endpoint does NOT include descriptions. Must fetch each job individually. Returns HTML-encoded content - decode with `html.unescape()` before BeautifulSoup.
- **Lever**: Returns full job data including description. May include HTML - strip with BeautifulSoup.
- **HN**: Parses monthly "Who is hiring?" threads via HN Algolia API.
- **SerpApi + SearchDiscovery**: SearchDiscovery uses SerpApi to find new company career pages via `site:` queries, then SerpApi collects from Google Jobs index.
- **ATS Collectors (Ashby, Workday, SmartRecruiters)**: Query public career page APIs for configured company boards.

**Rate Limiting:**

All collectors implement rate limiting to avoid bot detection:
- **Semaphore-based concurrency**: Limits concurrent requests (default: 5)
- **Random delays**: Waits 0.5-1.5 seconds between requests (configurable)
- **Inter-collector delays**: 5-15 second random delay between different collectors

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

**Scorer Protocol:** The `Scorer` protocol (`src/matching/scorer_protocol.py`) defines a pluggable interface. The heuristic `KeywordMatcher` is the current implementation. Config setting `scoring_engine` (heuristic/ai/hybrid) selects the engine via `get_scorer()`.

---

### 3. Deduplication (`src/dedup/`)

Prevents seeing the same job multiple times:

```
Job → Generate Fingerprint → Check Database → New? → Save

fingerprint = normalize(company) + ":" + normalize(title)
Example: "stripe:senior ai product manager"
```

- 30-day lookback window
- Fingerprints stored in database
- Batch dedup within same scan

---

### 4. Database Schema

**Models (9 total):**

| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `User` | Multi-tenant account | email, username, password_hash, google_id, tier |
| `UserProfile` | Job search preferences | target_titles, keywords, compensation (JSON) |
| `Job` | Job posting from radar | title, company, description, match_score, fingerprint |
| `Resume` | Resume versions | name, version, target_roles, is_active |
| `Application` | Job application | company, position, status, job_description, job_id |
| `Interview` | Interview record | round, type, scheduled_at, outcome |
| `EmailImport` | Imported email | gmail_message_id, email_type, parsed_data |
| `StatusHistory` | Status audit trail | old_status, new_status, changed_at |

All models except User/UserProfile have `user_id` (nullable) for multi-tenant readiness.

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
| Interview | "schedule an interview", calendly.com links, strong scheduling signals |
| Offer | "pleased to offer", "extend an offer" |

**Email → Application Linking:**

When an email is processed, `create_from_email()` automatically:
1. Finds or creates the Application by company name
2. Infers the source from the email sender domain (maps 30+ ATS domains like `greenhouse-mail.io` → "greenhouse", `ashbyhq.com` → "ashby")
3. Calls `_try_link_to_job()` to link to a Job record by company name (exact + fuzzy matching)
4. Copies `Job.description` to `Application.job_description` for analysis
5. Updates status based on email type (rejection, interview invite, offer)

**Email Parser Validation:**
- Company names are validated: rejects names >50 chars or containing sentence fragments
- Positions are cleaned: strips "the" prefix, rejects email boilerplate phrases
- Source is inferred from sender domain rather than defaulting to "email_import"

---

### 6. Rejection Analysis (`src/analytics/rejection_analysis.py`)

Analyzes rejected applications to identify resume gaps:

**How job descriptions auto-link:**
- `_try_link_to_job()` matches Application to Job by company name (case-insensitive, most recent first)
- Sets `application.job_id` and copies `Job.description` to `application.job_description`
- Called automatically during email processing and on rejection

**Analysis outputs:**
- Missing keywords (in job descriptions but not in your profile)
- Top required skills across rejections
- Common requirement phrases
- Per-application keyword match percentage

**Dashboard caching:** Analysis is cached for 5 minutes (`@st.cache_data(ttl=300)`) to avoid repeated expensive queries.

---

### 7. Settings Dashboard (`dashboard/pages/6_settings.py`)

Allows editing job search criteria directly from the web UI:
- Target titles (primary/secondary)
- Required/negative keywords
- Salary range
- Target companies by tier

Changes are written back to `config/profile.yaml`.

---

### 8. Analytics — Effective Stage Funnel

The funnel analytics (`src/analytics/funnel.py`) uses **highest stage reached** rather than current status.
This ensures applications rejected after interviewing still count in the interview stage of the funnel.

**How it works:**

For each application, `_get_highest_stage()` checks (in priority order):
1. Current status (if not terminal: rejected/withdrawn/ghosted)
2. `rejected_at` field (set when an app is rejected, records the stage it was in)
3. Linked `Interview` records (if any exist → at least phone_screen)
4. Linked `interview_invite` emails (same signal as Interview records)
5. `current_stage` field (more specific stage info like "Phone Screen", "HM Interview")

---

### 9. Onboarding System (`src/onboarding/`)

Helps new users configure Job Radar on first run.

| File | Purpose |
|------|---------|
| `validators.py` | Pydantic models for profile validation |
| `profile_builder.py` | Fluent builder pattern for config |
| `config_writer.py` | Writes profile.yaml and .env |
| `config_checker.py` | First-run detection |

**Setup Wizard Flow** (`dashboard/pages/0_setup.py`):
1. Welcome - Overview
2. Basic Info - Name, experience, remote preference
3. Job Titles - Primary and secondary target roles
4. Keywords - Required/negative keywords
5. Salary - Compensation range
6. Location - Preferred locations
7. Companies - Target companies by tier
8. Notifications - Slack webhook with test button
9. Review & Save - Confirm and write files

---

### 10. Database Migration

`init_db()` in `src/persistence/database.py` includes an auto-migration step (`_migrate_add_user_id_columns()`)
that checks for missing `user_id` columns on startup and adds them via `ALTER TABLE` if needed.
This handles databases created before multi-tenant support was added to the ORM models.

---

### 11. Enrichment Pipeline (`src/pipeline/enricher.py`)

Defines an `Enricher` protocol for post-scoring job enhancement. The default `NoOpEnricher` passes data through unchanged. Future enrichers (AI summary, semantic re-scoring) implement the same interface.

Hook point: after dedup, before notification in `src/main.py`.

---

## Deployment Options

### Option 1: Docker (Recommended)

```bash
./docker-start.sh   # Start dashboard + scanner
./docker-stop.sh    # Stop everything
```

**Services:**
- `dashboard` - Streamlit UI at http://localhost:8501
- `scanner` - Background job radar

**Data:** Docker uses PostgreSQL (data persisted in a Docker volume). Local dev uses SQLite at `./data/job_radar.db`.

### Option 2: Local with launchd (macOS)

```bash
cp launchd/com.jobradar.plist.example ~/Library/LaunchAgents/com.jobradar.plist
launchctl load ~/Library/LaunchAgents/com.jobradar.plist
```

### Option 3: GitHub Actions (Cloud)

Runs scanner every 30 minutes with Supabase PostgreSQL. See `.github/workflows/job-scan.yml`.

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Language | Python 3.12 | Core runtime |
| Web Framework | Streamlit | Dashboard UI |
| Database | PostgreSQL (Docker) / SQLite (local) + SQLAlchemy 2.0 | Persistence |
| Scheduler | APScheduler | Background jobs |
| HTTP Client | aiohttp | Async API calls |
| Charts | Plotly | Analytics |
| Notifications | Slack SDK | Webhook messages |
| Email | Google API | Gmail integration |
| Config | Pydantic | Settings validation |
| Containers | Docker Compose | Deployment |

---

## Security

1. **Credentials** - `.env`, `credentials.json`, `token.json` excluded from git via `.gitignore`
2. **XSS Protection** - `sanitize_html()` in `dashboard/common.py` escapes user data in all `unsafe_allow_html` calls
3. **LIKE Injection** - `_escape_like()` in `ApplicationService` escapes `%` and `_` wildcards in LIKE queries
4. **SQL Injection** - SQLAlchemy parameterized queries throughout; tested in `tests/security/test_sql_injection.py`
5. **Rate Limiting** - Collectors have built-in delays; `RateLimiter` utility in `src/auth/rate_limit.py`
6. **Data Privacy** - All data stored locally, no external sharing, Gmail read-only access

---

## Test Structure

356 tests organized as:

| File | Tests | Coverage |
|------|-------|----------|
| `test_onboarding.py` | 48 | Setup wizard validation |
| `test_gmail.py` | - | Email parser & classification |
| `test_matching.py` | - | Keyword matcher, scorer, protocol, title gating |
| `test_collectors.py` | - | Collector parsing |
| `test_analytics.py` | - | Funnel & source analytics |
| `test_services.py` | - | Application/resume services, _try_link_to_job |
| `test_models.py` | - | ORM model tests |
| `test_audit_fixes.py` | 51 | Analytics accuracy, data quality, source inference |
| `test_infrastructure.py` | - | Logging, database, collector infrastructure |
| `unit/test_auth_service.py` | - | Auth registration, login, OAuth |
| `unit/test_user_model.py` | - | User model & relationships |
| `security/test_data_isolation.py` | - | Multi-tenant data isolation |
| `security/test_sql_injection.py` | - | SQL injection + LIKE escaping |

Run all: `pytest tests/ -v`
