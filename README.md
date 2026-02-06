# Job Radar + Application Tracker

A complete job search automation system with real-time job monitoring, application tracking, and analytics. Clone it, configure your profile, and let it work for you.

## Features

### Job Radar
- Real-time monitoring of multiple job boards (RemoteOK, Greenhouse, Lever, Adzuna, HN Who's Hiring)
- Description-centric scoring algorithm (prioritizes job description keywords over title matching)
- Automatic deduplication with fingerprint-based 30-day lookback
- Optional Slack notifications for high-quality matches

### Application Tracker
- Track all job applications with full status history
- Resume version management and performance analytics
- Gmail integration to auto-import application confirmations, rejections, and interview invites
- Pipeline visualization (Kanban board)
- Source effectiveness analysis
- Funnel metrics and conversion tracking

### Rejection Analysis
- Auto-links applications to discovered jobs by company name
- Extracts missing skills and keyword gaps from rejected job descriptions
- Recommendations for resume improvements based on rejection patterns

### Settings Dashboard
- Edit target titles, keywords, salary, and companies directly from the web UI
- No need to manually edit YAML files after initial setup

## Prerequisites

- **Python 3.11+**
- **Git**
- **Docker** (optional, recommended)

## Quick Start

### Option A: Docker (Recommended)

```bash
# Fork this repo on GitHub, then clone your fork
git clone https://github.com/<your-username>/job-radar.git
cd job-radar

# Copy example config files
cp .env.example .env
cp config/profile.yaml.example config/profile.yaml

# Edit .env and config/profile.yaml with your settings

# Start both dashboard and scanner
./docker-start.sh
```

Open http://localhost:8501 in your browser. The Setup Wizard will guide you through the rest.

### Option B: Manual Setup

```bash
git clone https://github.com/<your-username>/job-radar.git
cd job-radar

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Copy example config files
cp .env.example .env
cp config/profile.yaml.example config/profile.yaml

# Edit .env and config/profile.yaml with your settings

# Run the dashboard
streamlit run dashboard/app.py
```

Open http://localhost:8501 in your browser. Complete the **Setup Wizard** on first run.

### Complete Setup Wizard

On first run, you'll be prompted to complete the **Setup Wizard** which guides you through:

1. **Basic Info** - Your name, experience, remote preference
2. **Job Titles** - Target roles (e.g., "Senior Product Manager")
3. **Keywords** - Required/negative keywords for matching
4. **Salary** - Compensation range
5. **Location** - Preferred locations
6. **Companies** - Target companies by tier
7. **Notifications** - Slack webhook URL (optional)

The wizard creates `config/profile.yaml` and updates `.env` automatically.

## Docker

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

## Running the Job Radar

```bash
# Run once
python src/main.py

# Or install as a macOS background service
./scripts/install_launchd.sh
```

## Set Up Slack Notifications (Optional)

```bash
python scripts/setup_slack.py
```

See [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) for detailed Slack and Gmail setup instructions.

## Set Up Gmail Integration (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project and enable Gmail API
3. Create OAuth credentials (Desktop app)
4. Download `credentials.json` to the project root
5. Run setup:

```bash
python scripts/setup_gmail.py
```

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
job-radar/
├── config/
│   ├── settings.py            # Application settings (Pydantic)
│   └── profile.yaml           # Job search criteria (from profile.yaml.example)
├── src/
│   ├── main.py                # Scheduler entry point (APScheduler)
│   ├── collectors/            # Job source collectors (RemoteOK, Greenhouse, Lever, etc.)
│   ├── matching/              # Description-centric keyword matching & scoring
│   ├── dedup/                 # Fingerprint-based deduplication
│   ├── notifications/         # Slack notifications
│   ├── persistence/           # SQLAlchemy models & database
│   ├── gmail/                 # Gmail OAuth + email parser
│   ├── tracking/              # Application & resume services
│   ├── analytics/             # Funnel, source, rejection, resume analytics
│   ├── onboarding/            # Setup wizard (validators, builder, config writer)
│   └── auth/                  # Auth service (scaffold, not active)
├── dashboard/
│   ├── app.py                 # Main Streamlit app
│   ├── common.py              # Shared init (path setup, init_db)
│   ├── pages/                 # Dashboard pages (0-6)
│   └── components/            # Reusable UI components
├── scripts/
│   ├── bootstrap.py           # Shared path setup for scripts
│   ├── setup_gmail.py         # Gmail OAuth setup
│   ├── setup_slack.py         # Slack webhook setup
│   ├── backfill_job_descriptions.py  # Backfill missing job descriptions
│   ├── reprocess_emails.py    # Re-parse existing emails
│   ├── import_historical.py   # Historical email import
│   └── run_scan.py            # One-time scan (for CI)
├── tests/                     # Test suite (200+ tests)
├── docs/
│   ├── ARCHITECTURE.md        # System architecture
│   └── SETUP_GUIDE.md         # Detailed setup instructions
└── launchd/
    └── com.jobradar.plist.example  # macOS service template
```

## Configuration

### Profile (config/profile.yaml)

Customize your job search criteria:

- `target_titles`: Job titles to match (primary and secondary)
- `required_keywords`: Keywords that must appear in listings
- `negative_keywords`: Keywords to exclude (checked against title only)
- `compensation`: Salary range preferences
- `target_companies`: Companies organized by tier (1-3)

### Job Sources

The radar collects from:

| Source | Type | Notes |
|--------|------|-------|
| RemoteOK | API | Remote-only jobs |
| Greenhouse | API | 130+ tech company boards |
| Lever | API | 75+ startup boards |
| HN Who's Hiring | API | Monthly thread via Algolia |
| Adzuna | API | Requires API key (optional) |

## Dashboard Pages

1. **Home** - Overview metrics, recent applications, top job matches, funnel chart
2. **Jobs** - Browse and filter job matches by score, source, company
3. **Applications** - Track applications, add interviews, manage resumes
4. **Pipeline** - Kanban-style board with quick status actions
5. **Analytics** - Funnel, source effectiveness, resume performance
6. **Rejection Analysis** - Skill gap analysis from rejected job descriptions
7. **Settings** - Edit titles, keywords, salary, companies from the dashboard

## Commands

```bash
# Run radar once
python src/main.py

# Run dashboard
streamlit run dashboard/app.py

# Backfill job descriptions for existing applications
python scripts/backfill_job_descriptions.py --dry-run

# Test Slack notifications
python scripts/setup_slack.py

# Check Gmail connection
python scripts/setup_gmail.py

# Import historical emails
python scripts/import_historical.py

# Install as macOS service
./scripts/install_launchd.sh

# Run tests
pytest tests/ -v
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook | No (enables Slack alerts) |
| `DATABASE_URL` | SQLAlchemy database URL | No (default: sqlite:///data/job_radar.db) |
| `GMAIL_CREDENTIALS_FILE` | Path to Google OAuth credentials | For Gmail |
| `ADZUNA_APP_ID` | Adzuna API app ID | For Adzuna |
| `ADZUNA_APP_KEY` | Adzuna API key | For Adzuna |
| `JOB_CHECK_INTERVAL_MINUTES` | How often to scan for jobs | No (default: 30) |
| `EMAIL_CHECK_INTERVAL_MINUTES` | How often to check email | No (default: 15) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, running tests, and PR guidelines.

## License

MIT - see [LICENSE](LICENSE)
