# Job Radar Setup Guide

This guide walks you through setting up Slack notifications and Gmail integration.

---

## Part 1: Slack Webhook Setup

Slack webhooks let Job Radar send you instant alerts when high-quality jobs are found.

### Step 1: Create a Slack App

1. Go to **https://api.slack.com/apps**
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Enter:
   - **App Name:** `Job Radar`
   - **Workspace:** Select your personal workspace (or create one at slack.com)
5. Click **"Create App"**

### Step 2: Enable Incoming Webhooks

1. In the left sidebar, click **"Incoming Webhooks"**
2. Toggle **"Activate Incoming Webhooks"** to **ON**
3. Click **"Add New Webhook to Workspace"**
4. Select the channel where you want job alerts (e.g., `#job-search` or `#general`)
5. Click **"Allow"**

### Step 3: Copy the Webhook URL

After authorization, you'll see a webhook URL like:
```
https://hooks.slack.com/services/TXXXXX/BXXXXX/your-webhook-token
```

**Copy this URL** - you'll need it in the next step.

### Step 4: Configure Job Radar

1. Open your `.env` file:
   ```bash
   cd path/to/job-radar
   nano .env
   ```

2. Update the `SLACK_WEBHOOK_URL` line:
   ```
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/TXXXXX/BXXXXX/your-webhook-token
   ```

3. Save and exit (Ctrl+X, Y, Enter in nano)

### Step 5: Test the Webhook

```bash
cd path/to/job-radar
source venv/bin/activate
python scripts/setup_slack.py
```

You should see "Webhook is working!" and receive a test message in Slack.

### Slack Notification Settings

You can customize when you receive notifications in `config/profile.yaml`:

```yaml
notifications:
  slack:
    enabled: true
    min_score: 60  # Only notify for scores >= 60
```

---

## Part 2: Gmail Integration Setup

Gmail integration automatically imports application confirmations, rejections, and interview invitations.

### Step 1: Create a Google Cloud Project

1. Go to **https://console.cloud.google.com**
2. Click the project dropdown at the top → **"New Project"**
3. Enter:
   - **Project name:** `Job Radar`
   - **Organization:** Leave as default
4. Click **"Create"**
5. Wait for the project to be created, then select it

### Step 2: Enable the Gmail API

1. In the search bar, type **"Gmail API"**
2. Click on **"Gmail API"** in the results
3. Click **"Enable"**

### Step 3: Configure OAuth Consent Screen

1. In the left sidebar, go to **"APIs & Services"** → **"OAuth consent screen"**
2. Select **"External"** (unless you have a Google Workspace)
3. Click **"Create"**
4. Fill in:
   - **App name:** `Job Radar`
   - **User support email:** Your email
   - **Developer contact email:** Your email
5. Click **"Save and Continue"**
6. On the Scopes page, click **"Add or Remove Scopes"**
7. Find and check:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.labels`
8. Click **"Update"** then **"Save and Continue"**
9. On Test Users, click **"Add Users"**
10. Add your Gmail address
11. Click **"Save and Continue"**

### Step 4: Create OAuth Credentials

1. In the left sidebar, go to **"APIs & Services"** → **"Credentials"**
2. Click **"+ Create Credentials"** → **"OAuth client ID"**
3. Select:
   - **Application type:** Desktop app
   - **Name:** `Job Radar Desktop`
4. Click **"Create"**
5. Click **"Download JSON"**
6. Rename the downloaded file to `credentials.json`
7. Move it to the project root:
   ```bash
   mv ~/Downloads/credentials.json path/to/job-radar/
   ```

### Step 5: Authenticate with Gmail

```bash
cd path/to/job-radar
source venv/bin/activate
python scripts/setup_gmail.py
```

This will:
1. Open a browser window
2. Ask you to sign in to Google
3. Show a warning about unverified app (click "Advanced" → "Go to Job Radar")
4. Ask for Gmail permissions
5. Save a token locally for future use

### Step 6: Import Historical Emails

To import all job-related emails since your layoff date (Jan 20, 2025):

```bash
python scripts/import_historical.py
```

This will:
- Search for application confirmations, rejections, and interview invites
- Create Application records automatically
- Link emails to applications

### Gmail Configuration

In `.env`:
```
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json
```

---

## Verification Checklist

### Slack
- [ ] Created Slack app at api.slack.com
- [ ] Enabled Incoming Webhooks
- [ ] Added webhook to a channel
- [ ] Copied webhook URL to `.env`
- [ ] Ran `python scripts/setup_slack.py` successfully
- [ ] Received test message in Slack

### Gmail
- [ ] Created Google Cloud project
- [ ] Enabled Gmail API
- [ ] Configured OAuth consent screen
- [ ] Created OAuth credentials (Desktop app)
- [ ] Downloaded `credentials.json` to project root
- [ ] Ran `python scripts/setup_gmail.py` successfully
- [ ] Ran `python scripts/import_historical.py` to import emails

---

## Quick Reference

### Start Everything

```bash
cd path/to/job-radar
source venv/bin/activate

# Terminal 1: Run the dashboard
streamlit run dashboard/app.py

# Terminal 2: Run job radar (optional - for live scanning)
python src/main.py
```

### File Locations

| File | Location |
|------|----------|
| Slack webhook | `.env` → `SLACK_WEBHOOK_URL` |
| Gmail credentials | `credentials.json` (project root) |
| Gmail token | `token.json` (auto-created) |
| Database | `job_radar.db` (project root) |
| Logs | `logs/jobradar.log` |

### Troubleshooting

**"Gmail not authenticated"**
→ Run `python scripts/setup_gmail.py` again

**"Slack webhook test failed"**
→ Check the webhook URL in `.env` is correct (no quotes needed)

**"No jobs found"**
→ Check your internet connection and try running `python src/main.py`

**"Module not found"**
→ Make sure you activated the venv: `source venv/bin/activate`
