# Job Radar - Claude Context

## Project Overview

Job Radar is a complete job search automation system for Sam Montoya, a Senior/Lead/Staff AI Product Manager. The system has two main components:

1. **Job Radar** - Background service that monitors job boards, scores matches, and sends Slack alerts
2. **Application Tracker** - Web dashboard for tracking applications, resumes, interviews, and analytics

## User Profile

- **Name:** Sam Montoya
- **Target Roles:** AI Product Manager, Senior/Lead/Staff/Principal PM, Director of Product
- **Focus Areas:** Search, Discovery, Personalization, Recommendations, GenAI, Agentic AI, LLMs
- **Salary Range:** $185k-$225k (flexible)
- **Preference:** Remote
- **Experience:** 8+ years
- **Layoff Date:** January 20, 2026
- **Former Employer:** Weedmaps (laid off)

## Key Files

| File | Purpose |
|------|---------|
| `config/profile.yaml` | Job search criteria, keywords, target companies |
| `config/settings.py` | Environment settings (Pydantic) |
| `src/main.py` | Scheduler entry point |
| `dashboard/app.py` | Streamlit dashboard entry |
| `.env` | Secrets (Slack webhook, Gmail paths) |
| `src/persistence/cleanup.py` | Data retention (60-day cleanup, description truncation) |
| `src/analytics/rejection_analysis.py` | Analyze rejected applications for resume gaps |
| `src/gmail/parser.py` | Email classification and company extraction |
| `scripts/run_scan.py` | One-time scan for GitHub Actions |
| `scripts/reprocess_emails.py` | Re-parse and link existing emails |
| `scripts/bootstrap.py` | Shared path setup for all scripts |
| `.github/workflows/job-scan.yml` | GitHub Actions workflow (every 30 min) |
| `src/collectors/utils.py` | Shared utilities (parse_salary, parse_date, detect_remote) |
| `dashboard/common.py` | Shared dashboard initialization (path setup, init_db) |
| `docker-compose.yml` | Docker service orchestration |
| `docker-start.sh` | Easy Docker start script |
| `docker-stop.sh` | Easy Docker stop script |
| `docs/ARCHITECTURE.md` | System architecture documentation |

## Running the Project

```bash
# Always activate venv first
cd /Users/sammontoya/job-hunt/job-radar
source venv/bin/activate

# Run dashboard
streamlit run dashboard/app.py

# Run job radar (background scanning)
python src/main.py
```

### Background Service (launchd)

Job Radar runs as a background service via launchd:

```bash
# Load service (starts at login)
launchctl load ~/Library/LaunchAgents/com.sammontoya.jobradar.plist

# Unload service
launchctl unload ~/Library/LaunchAgents/com.sammontoya.jobradar.plist

# Check status
launchctl list | grep jobradar

# View logs
tail -f logs/jobradar.log
```

The plist is located at `launchd/com.sammontoya.jobradar.plist`. Copy to `~/Library/LaunchAgents/` to enable.

### Docker (Recommended)

Run both the dashboard and scanner in Docker containers:

```bash
# Start (builds and runs in background)
./docker-start.sh

# Stop
./docker-stop.sh

# View logs
docker compose logs -f
docker compose logs -f dashboard
docker compose logs -f scanner

# Restart just one service
docker compose restart scanner
```

**Services:**
- `dashboard` - Streamlit web UI at http://localhost:8501
- `scanner` - Background job radar (checks every 30 min by default)

**Data persistence:**
- Database stored in `./data/job_radar.db`
- Logs stored in `./logs/`
- Config mounted from `./config/profile.yaml`

**Files:**
| File | Purpose |
|------|---------|
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | Service orchestration |
| `docker-start.sh` | Easy start script |
| `docker-stop.sh` | Easy stop script |

### GitHub Actions Deployment (Alternative)

For cloud deployment, GitHub Actions runs the scanner every 30 minutes with Supabase PostgreSQL:

1. Create Supabase account at supabase.com
2. Get connection string: Settings → Database → Connection string → URI
3. Add GitHub secrets: `DATABASE_URL`, `SLACK_WEBHOOK_URL`
4. Push to public repo for free Actions minutes

The workflow is at `.github/workflows/job-scan.yml`. Gmail import is disabled in CI (requires OAuth).

**Storage optimization:** Job descriptions truncated to 2,000 chars. Jobs older than 60 days auto-deleted (except applied/saved).

### GitHub Repository

**URL:** https://github.com/smontoya86/job-radar (public)

**Secrets required for GitHub Actions:**
- `DATABASE_URL` - Supabase PostgreSQL connection string
- `SLACK_WEBHOOK_URL` - Slack webhook URL

**Files excluded from repo (in .gitignore):**
- `.env` - Environment secrets
- `credentials.json` / `token.json` - Gmail OAuth
- `job_radar.db` - Local database
- `config/profile.yaml` - Personal job search profile
- `launchd/com.sammontoya.jobradar.plist` - Personal launchd config

**Template files provided:**
- `.env.example`, `config/profile.yaml.example`, `launchd/com.jobradar.plist.example`

## Common Issues & Solutions

### 1. Import Errors
**Problem:** `ModuleNotFoundError` for various packages
**Solution:** Always activate the virtual environment first:
```bash
source venv/bin/activate
```
The venv contains all dependencies. System Python doesn't have them.

### 2. Path Issues
**Problem:** Imports fail when running from different directories
**Solution:** Scripts add project root to sys.path:
```python
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
```

### 3. Gmail Not Authenticated
**Problem:** Gmail features fail
**Solution:** Run `python scripts/setup_gmail.py` to complete OAuth flow

### 4. Slack Notifications Not Working
**Problem:** No Slack messages received
**Solution:**
1. Check `.env` has `SLACK_WEBHOOK_URL` set
2. Run `python scripts/setup_slack.py` to test

### 5. Database Issues
**Problem:** Missing tables or schema errors
**Solution:** `init_db()` is called automatically but can be forced:
```python
from src.persistence.database import init_db
init_db()
```

## Architecture Patterns

### Collectors Pattern
All collectors inherit from `BaseCollector` and implement async `collect()`:
```python
class MyCollector(BaseCollector):
    name = "my_source"

    async def collect(self, search_queries: list[str]) -> list[JobData]:
        # Fetch and return JobData objects
```

### Service Pattern
Services (`ApplicationService`, `ResumeService`) take a database session:
```python
with get_session() as session:
    service = ApplicationService(session)
    app = service.create_application(...)
```

### Settings Access
```python
from config.settings import settings
print(settings.slack_webhook_url)
print(settings.database_url)
```

## Database

- **Location:** `job_radar.db` (SQLite, created in project root)
- **ORM:** SQLAlchemy 2.0 with declarative models
- **Models:** Job, Application, Resume, Interview, EmailImport, StatusHistory

## Dependencies

Key packages (all in venv):
- `python-jobspy` - Multi-site job scraping
- `aiohttp` - Async HTTP
- `sqlalchemy` - Database ORM
- `streamlit` - Dashboard UI
- `apscheduler` - Background scheduling
- `slack-sdk` - Slack integration
- `google-api-python-client` - Gmail API

## Testing Changes

Quick validation:
```bash
source venv/bin/activate
python -c "
from config.settings import settings
from src.persistence.database import init_db
init_db()
print('OK')
"
```

## Lessons Learned

### Environment & Setup
1. **Always use virtual environment** - macOS has externally-managed Python that won't allow pip installs
2. **Check all imports before delivery** - Run a quick import test to catch missing dependencies
3. **Path handling is critical** - Use `Path(__file__).parent` patterns for reliable imports
4. **Collectors may fail silently** - They return empty lists on error; check logs

### Asyncio & Background Services
5. **Asyncio event loop in launchd** - When running as a service, use `asyncio.run(async_main())` pattern. Don't create event loops manually with `get_event_loop()` as it fails when there's no running loop
6. **Python unbuffered output for launchd** - Use `-u` flag in plist command to see output immediately in logs

### Job Description Parsing
7. **Greenhouse API quirk** - The list endpoint `/v1/boards/{company}/jobs` does NOT include job descriptions. Must make separate calls to `/v1/boards/{company}/jobs/{id}` for each job to get full content
8. **HTML entity encoding** - Greenhouse API returns HTML-encoded content (`&lt;` instead of `<`). Must call `html.unescape()` BEFORE BeautifulSoup to properly strip tags
9. **Job ID extraction** - Greenhouse URLs use query params (`?gh_jid=12345`), not path segments. Parse carefully and store job_id in extra_data during initial fetch

### Matching Algorithm
10. **Description > Title** - A "Staff PM" with AI-heavy description is more relevant than "AI PM" with generic description. The description-centric algorithm weights description keywords at 40% vs title at 20%
11. **Keyword variety matters** - Jobs mentioning multiple different keywords (AI, ML, search) are more relevant than ones repeating the same keyword

### Email Parser
12. **Extract company from subject, not domain** - ATS emails (greenhouse-mail.io, ashbyhq.com, rippling.com) have useless subdomains. Parse subject lines like "Thank you from {Company}" or "{Company} Update" instead
13. **Interview detection needs strong signals** - Weak signals like "next step" cause false positives. Require scheduling links (calendly, google calendar) or explicit phrases ("Interview Request", "Phone Screen") for interview_invite classification
14. **Negative signals prevent false positives** - Phrases like "if we decide to move forward" or "your application was sent" indicate NOT an interview invite

### Streamlit
15. **Module caching issues** - Streamlit caches imported modules. When adding new methods to existing classes, must fully restart Streamlit (Ctrl+C and restart), not just reload. Clear `__pycache__` if issues persist
16. **Background tasks for dashboard** - Use `run_in_background=true` when starting Streamlit from scripts to avoid blocking
17. **Path setup required before imports** - Streamlit pages need `sys.path.insert()` before importing from `dashboard.common` because Streamlit doesn't run from project root

### Refactoring & Code Quality
18. **Extract shared utilities** - Common patterns (salary parsing, date parsing, remote detection) were duplicated across 5+ collectors. Extracted to `src/collectors/utils.py`
19. **Bootstrap modules for scripts** - All scripts had identical 5-line path setup. Extracted to `scripts/bootstrap.py`
20. **Dashboard common module** - All dashboard pages had identical init code. Extracted to `dashboard/common.py` (calls `init_db()` on import)
21. **Deprecation warnings are breaking changes** - Streamlit's `use_container_width` deprecation will break after 2025-12-31. Fix early with `width="stretch"`
22. **datetime.utcnow() deprecated** - Use `datetime.now(timezone.utc)` instead

### GitHub & Security
23. **GitHub secret scanning** - Push protection blocks webhook URLs even in docs. Use clearly fake placeholders like `TXXXXX/BXXXXX/your-webhook-token`
24. **gitignore before first commit** - Add sensitive files to .gitignore BEFORE staging, or use `git rm --cached` to unstage
25. **Template files for config** - Create `.example` versions of config files with placeholder values for public repos
26. **Home directory git repos** - Check for `.git` in parent directories; can cause git to track unintended files

### Docker
27. **Port conflicts** - Stop local services before starting Docker (e.g., local Streamlit on 8501 blocks Docker dashboard)
28. **Data persistence** - Mount volumes for database (`./data`) so data survives container restarts
29. **Optional file mounts** - Use `touch` to create empty placeholder files for optional mounts (credentials.json, token.json) to avoid mount errors
30. **Health checks** - Use Python urllib instead of curl for health checks (smaller image, no extra install)
31. **Unbuffered Python in Docker** - Use `python -u` flag in container commands for real-time log output

### Documentation
32. **Single source of truth** - Keep only one ARCHITECTURE.md (in docs/). Duplicates drift out of sync (e.g., old vs new scoring algorithm)

## Application Statuses

Simplified status workflow:
- `applied` - Initial application submitted
- `phone_screen` - Recruiter/phone screen scheduled or completed
- `interviewing` - Active interview process (HM, panel, onsite)
- `offer` - Received offer
- `accepted` - Accepted offer
- `rejected` - Rejected at any stage
- `withdrawn` - Withdrew application
- `ghosted` - No response after 2+ weeks

## Interview Types

Tracked interview types for analytics:
- Phone Screen
- HM Interview (Hiring Manager)
- Product Sense
- Technical
- Behavioral
- Panel
- Onsite
- Take Home
- Final Round
- Other

## Scoring Algorithm

**Description-Centric Scoring (v2)** - Prioritizes job description analysis:

| Component | Weight | Description |
|-----------|--------|-------------|
| Description Keywords | 40% | Primary/secondary keywords found in job description |
| Title Relevance | 20% | Exact match or partial credit for related titles |
| Keyword Variety | 15% | Bonus for mentioning multiple different keywords |
| Company Tier | 15% | Tier 1 = 100%, Tier 2 = 70%, Tier 3 = 40% |
| Salary/Remote | 10% | 5% each for matching preferences |

The key insight: A "Staff PM" role with AI/ML-heavy description should score higher than an "AI PM" with a generic description.

## Future Improvements

- [ ] Add more Greenhouse/Lever companies to default lists
- [ ] Implement email digest (daily summary)
- [ ] Add interview reminder notifications
- [ ] Browser extension for quick application logging
- [ ] Resume parsing to auto-detect which version was used
