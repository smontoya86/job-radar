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
│         │                  │                  │                  │         │
│         ▼                  ▼                  ▼                  ▼         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         SQLite DATABASE                             │   │
│  │  ┌─────────┐  ┌──────────────┐  ┌─────────┐  ┌────────────────┐    │   │
│  │  │  Jobs   │  │ Applications │  │ Resumes │  │ Email Imports  │    │   │
│  │  └─────────┘  └──────────────┘  └─────────┘  └────────────────┘    │   │
│  │                      │                              ▲               │   │
│  │                      │                              │               │   │
│  └──────────────────────┼──────────────────────────────┼───────────────┘   │
│                         │                              │                   │
├─────────────────────────┼──────────────────────────────┼───────────────────┤
│                         │    APPLICATION TRACKER       │                   │
├─────────────────────────┼──────────────────────────────┼───────────────────┤
│                         │                              │                   │
│                         ▼                              │                   │
│  ┌─────────────────────────────────────────────────────┼───────────────┐   │
│  │                    STREAMLIT DASHBOARD              │               │   │
│  │  ┌─────────┐  ┌──────────────┐  ┌──────────┐  ┌────┴─────┐        │   │
│  │  │  Jobs   │  │ Applications │  │ Pipeline │  │ Analytics │        │   │
│  │  │  Page   │  │    Page      │  │  Board   │  │   Page    │        │   │
│  │  └─────────┘  └──────────────┘  └──────────┘  └──────────┘        │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                        ▲                   │
│                                                        │                   │
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
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Deep Dive

### 1. Job Collectors (`src/collectors/`)

Each collector implements the `BaseCollector` interface:

```python
class BaseCollector(ABC):
    @abstractmethod
    async def collect(self, search_queries: list[str]) -> list[JobData]:
        pass
```

| Collector | Source | Method | Rate Limits | Notes |
|-----------|--------|--------|-------------|-------|
| `JobSpyCollector` | Indeed, LinkedIn, Glassdoor | Web scraping via python-jobspy | Moderate | Primary source, most jobs |
| `RemoteOKCollector` | remoteok.com | Public API | Low | Remote-only, no auth needed |
| `GreenhouseCollector` | Greenhouse boards | Public API | Low | 20+ tech companies configured |
| `LeverCollector` | Lever boards | Public API | Low | 20+ startups configured |
| `HNCollector` | Hacker News | API + scraping | Very low | Monthly "Who's Hiring" thread |
| `AdzunaCollector` | Adzuna | API (requires key) | Medium | Optional, needs signup |
| `WellfoundCollector` | Wellfound/AngelList | Web scraping | High | Startup jobs, rate limited |

**Data Flow:**
```
Search Queries → Collector → Raw Jobs → JobData objects
```

### 2. Matching & Scoring (`src/matching/`)

**KeywordMatcher** loads your profile and matches jobs:

```
profile.yaml
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│                    KeywordMatcher                         │
│  ┌─────────────────┐  ┌─────────────────┐                │
│  │ Primary Keywords│  │Secondary Keywords│                │
│  │ (must have 1+)  │  │ (bonus points)   │                │
│  │ • AI            │  │ • product manager│                │
│  │ • ML            │  │ • agentic        │                │
│  │ • search        │  │ • RAG            │                │
│  │ • personalization│ │ • NLP            │                │
│  └─────────────────┘  └─────────────────┘                │
│                                                           │
│  ┌─────────────────┐  ┌─────────────────┐                │
│  │Negative Keywords│  │ Company Tiers   │                │
│  │ (exclude)       │  │                 │                │
│  │ • junior        │  │ Tier 1: OpenAI  │                │
│  │ • intern        │  │ Tier 2: Stripe  │                │
│  │ • contract      │  │ Tier 3: Spotify │                │
│  └─────────────────┘  └─────────────────┘                │
└───────────────────────────────────────────────────────────┘
```

**Scoring Algorithm:**

| Component | Weight | Calculation |
|-----------|--------|-------------|
| Title Match | 35% | Binary - does title match target titles? |
| Keyword Match | 30% | (primary_matches/total_primary × 0.7) + (secondary_matches/total_secondary × 0.3) |
| Company Tier | 15% | Tier 1 = 100%, Tier 2 = 66%, Tier 3 = 33% |
| Salary Match | 10% | Binary - does salary overlap with range? |
| Remote Match | 10% | Binary - is remote if remote_only preference? |

**Score Thresholds:**
- 80+ = 🔥 Excellent Match
- 60-79 = ✨ Good Match
- 30-59 = 📋 Potential Match
- <30 = Not shown

### 3. Deduplication (`src/dedup/`)

Prevents seeing the same job multiple times:

```
Job → Generate Fingerprint → Check Database → New? → Save
                │
                ▼
        fingerprint = normalize(company) + ":" + normalize(title)

        Example: "stripe:senior ai product manager"
```

- 30-day lookback window
- Fingerprints stored in SQLite
- Batch dedup within same scan

### 4. Notifications (`src/notifications/`)

Slack webhook integration:

```
Scored Jobs (60+) → Format Message → POST to Webhook → Slack Channel
```

**Message Format:**
```
┌────────────────────────────────────────┐
│ 🔥 Excellent Match: 85/100             │
├────────────────────────────────────────┤
│ Senior AI Product Manager              │
│ Stripe ⭐⭐⭐                           │
├────────────────────────────────────────┤
│ Location: Remote 🏠                    │
│ Salary: $180,000 - $220,000           │
│ Source: linkedin                       │
│ Keywords: AI, ML, search, personalization│
├────────────────────────────────────────┤
│ [Apply Now]  [View Job]                │
└────────────────────────────────────────┘
```

### 5. Database Schema (`src/persistence/`)

```
┌─────────────────┐     ┌─────────────────┐
│      Jobs       │     │    Resumes      │
├─────────────────┤     ├─────────────────┤
│ id (PK)         │     │ id (PK)         │
│ title           │     │ name            │
│ company         │     │ version         │
│ location        │     │ file_path       │
│ description     │     │ target_roles    │
│ salary_min/max  │     │ key_changes     │
│ url             │     │ is_active       │
│ source          │     │ created_at      │
│ remote          │     └────────┬────────┘
│ match_score     │              │
│ matched_keywords│              │
│ fingerprint     │              │
│ status          │              │
│ discovered_at   │              │
│ notified_at     │              │
└────────┬────────┘              │
         │                       │
         │    ┌──────────────────┴──────────────────┐
         │    │           Applications              │
         │    ├─────────────────────────────────────┤
         └───▶│ id (PK)                             │
              │ job_id (FK) ─────────────────────────┘
              │ resume_id (FK) ──────────────────────┘
              │ company, position                   │
              │ applied_date                        │
              │ source                              │
              │ status                              │
              │ interview_rounds                    │
              │ rejected_at                         │
              │ offer_amount                        │
              └────────┬────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
         ▼                           ▼
┌─────────────────┐     ┌─────────────────┐
│   Interviews    │     │  EmailImports   │
├─────────────────┤     ├─────────────────┤
│ id (PK)         │     │ id (PK)         │
│ application_id  │     │ gmail_message_id│
│ round           │     │ subject         │
│ type            │     │ from_address    │
│ scheduled_at    │     │ email_type      │
│ interviewers    │     │ application_id  │
│ outcome         │     │ parsed_data     │
│ feedback        │     │ processed       │
└─────────────────┘     └─────────────────┘
```

### 6. Gmail Integration (`src/gmail/`)

**Authentication Flow:**
```
credentials.json → OAuth2 Flow → token.json → API Access
        │                              │
        │         Browser opens        │
        │         User authorizes      │
        ▼              │               ▼
   Google Cloud    ◀───┘         Stored locally
   Console                       for reuse
```

**Email Classification:**

| Type | Detection Patterns |
|------|-------------------|
| Confirmation | "thank you for applying", "application received" |
| Rejection | "after careful consideration", "decided to move forward with other" |
| Interview | "schedule an interview", "next steps", calendly.com |
| Offer | "pleased to offer", "extend an offer" |

### 7. Analytics (`src/analytics/`)

**Funnel Metrics:**
```
Applied ──────────────────────────────▶ 100% (45)
   │
   ▼
Screening ────────────────────────────▶ 40% (18)
   │
   ▼
Interview ────────────────────────────▶ 18% (8)
   │
   ▼
Offer ────────────────────────────────▶ 4% (2)
```

**Source Analysis:**
- Response rate by source (LinkedIn, Referral, etc.)
- Interview conversion rate
- Best performing channels

**Resume Analysis:**
- Response rate per resume version
- A/B comparison between versions
- Recommendations for which to use

---

## Data Flow: Complete Cycle

### Job Discovery Flow
```
1. Scheduler triggers (every 30 min)
           │
           ▼
2. Load profile.yaml → Generate search queries
           │
           ▼
3. Run all collectors in parallel
           │
           ▼
4. Score each job against profile
           │
           ▼
5. Deduplicate against database
           │
           ▼
6. Save new jobs to SQLite
           │
           ▼
7. Send Slack notifications (score >= 60)
```

### Application Tracking Flow
```
1. User applies to job (from dashboard or external)
           │
           ▼
2. Create Application record
           │
           ▼
3. Gmail imports confirmations/rejections
           │
           ▼
4. Auto-update application status
           │
           ▼
5. User adds interviews, updates status
           │
           ▼
6. Analytics track funnel progression
```

---

## Scheduler Architecture

Using APScheduler with AsyncIO:

```python
┌────────────────────────────────────────┐
│           AsyncIOScheduler             │
├────────────────────────────────────────┤
│                                        │
│  Job: run_job_scan                     │
│  Interval: 30 minutes                  │
│  Max Instances: 1                      │
│                                        │
│  Job: run_email_import                 │
│  Interval: 15 minutes                  │
│  Max Instances: 1                      │
│                                        │
└────────────────────────────────────────┘
```

For production, can run as macOS launchd service:
```
~/Library/LaunchAgents/com.sammontoya.jobradar.plist
    │
    ├── Runs at login
    ├── Auto-restarts on crash
    ├── Logs to logs/jobradar.log
    └── Background priority
```

---

## Technology Stack Summary

| Layer | Technology | Purpose |
|-------|------------|---------|
| Language | Python 3.11+ | Core runtime |
| Web Framework | Streamlit | Dashboard UI |
| Database | SQLite + SQLAlchemy | Persistence |
| Scheduler | APScheduler | Background jobs |
| HTTP Client | aiohttp | Async API calls |
| Job Scraping | python-jobspy | LinkedIn/Indeed/Glassdoor |
| Charts | Plotly | Analytics visualization |
| Notifications | Slack SDK | Webhook messages |
| Email | Google API | Gmail integration |
| Config | Pydantic | Settings validation |

---

## Security Considerations

1. **Credentials Storage**
   - `.env` file excluded from git
   - Gmail token.json excluded from git
   - credentials.json excluded from git

2. **Rate Limiting**
   - Collectors have built-in delays
   - Scheduler prevents overlapping runs
   - Max instances = 1 per job

3. **Data Privacy**
   - All data stored locally (SQLite)
   - No external data sharing
   - Gmail read-only access
