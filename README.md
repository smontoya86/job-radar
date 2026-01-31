# Job Radar + Application Tracker

A complete job search system with real-time job monitoring and application tracking.

## Features

### Job Radar
- Real-time monitoring of multiple job boards (Indeed, LinkedIn, Glassdoor, RemoteOK, Greenhouse, Lever, etc.)
- Keyword-based scoring and matching
- Automatic deduplication
- Instant Slack notifications for high-quality matches

### Application Tracker
- Track all job applications with status history
- Resume version management and performance analytics
- Gmail integration to auto-import application confirmations/rejections
- Pipeline visualization (Kanban board)
- Source effectiveness analysis
- Funnel metrics and conversion tracking

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/sammontoya/job-hunt/job-radar
python -m pip install -e .
```

### 2. Configure Environment

Copy the example environment file and edit with your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your:
- Slack webhook URL
- Gmail credentials path (if using Gmail import)
- Adzuna API keys (optional)

### 3. Set Up Slack Notifications (Recommended)

```bash
python scripts/setup_slack.py
```

### 4. Set Up Gmail Integration (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project and enable Gmail API
3. Create OAuth credentials (Desktop app)
4. Download `credentials.json` to the project root
5. Run setup:

```bash
python scripts/setup_gmail.py
```

### 5. Import Historical Emails (Optional)

If you want to import past job-related emails:

```bash
python scripts/import_historical.py
```

### 6. Run the Dashboard

```bash
streamlit run dashboard/app.py
```

Open http://localhost:8501 in your browser.

### 7. Run the Job Radar

```bash
python src/main.py
```

Or install as a background service (macOS):

```bash
./scripts/install_launchd.sh
```

## Project Structure

```
job-radar/
├── config/
│   ├── settings.py          # Application settings
│   └── profile.yaml         # Job search criteria
├── src/
│   ├── main.py              # Scheduler entry point
│   ├── collectors/          # Job source collectors
│   ├── matching/            # Keyword matching & scoring
│   ├── dedup/               # Deduplication
│   ├── notifications/       # Slack notifications
│   ├── persistence/         # Database models
│   ├── gmail/               # Gmail integration
│   ├── tracking/            # Application tracking
│   └── analytics/           # Analytics & metrics
├── dashboard/
│   ├── app.py               # Main Streamlit app
│   ├── pages/               # Dashboard pages
│   └── components/          # Reusable UI components
├── scripts/
│   ├── setup_gmail.py       # Gmail OAuth setup
│   ├── setup_slack.py       # Slack webhook setup
│   └── import_historical.py # Historical email import
└── launchd/
    └── com.sammontoya.jobradar.plist  # macOS service config
```

## Configuration

### Profile (config/profile.yaml)

Customize your job search criteria:

- `target_titles`: Job titles to match
- `required_keywords`: Keywords that must appear in listings
- `negative_keywords`: Keywords to exclude
- `compensation`: Salary range preferences
- `target_companies`: Companies organized by tier
- `scoring`: Weights for match scoring

### Job Sources

The radar collects from:

| Source | Type | Notes |
|--------|------|-------|
| Indeed | JobSpy | Requires no API key |
| LinkedIn | JobSpy | May require login |
| Glassdoor | JobSpy | Company reviews |
| RemoteOK | API | Remote-only jobs |
| Greenhouse | API | Tech companies |
| Lever | API | Startup focus |
| HN Who's Hiring | Scrape | Monthly thread |
| Adzuna | API | Requires API key |

## Dashboard Pages

1. **Home**: Overview metrics and quick stats
2. **Jobs**: Browse and filter job matches
3. **Applications**: Track and manage applications
4. **Pipeline**: Kanban-style application view
5. **Analytics**: Funnel, source, and resume analytics

## Commands

```bash
# Run radar once
python src/main.py

# Run dashboard
streamlit run dashboard/app.py

# Test Slack notifications
python scripts/setup_slack.py

# Check Gmail connection
python scripts/setup_gmail.py

# Import historical emails
python scripts/import_historical.py

# Install as macOS service
./scripts/install_launchd.sh

# View service logs
tail -f logs/jobradar.log
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook | Yes |
| `DATABASE_URL` | SQLite database path | No (default: sqlite:///job_radar.db) |
| `GMAIL_CREDENTIALS_FILE` | Path to Google OAuth credentials | For Gmail |
| `ADZUNA_APP_ID` | Adzuna API app ID | For Adzuna |
| `ADZUNA_APP_KEY` | Adzuna API key | For Adzuna |
| `JOB_CHECK_INTERVAL_MINUTES` | How often to scan for jobs | No (default: 30) |
| `EMAIL_CHECK_INTERVAL_MINUTES` | How often to check email | No (default: 15) |

## License

MIT
