# upwork-lead-dashboard
Upwork lead intelligence for Zero Touch AI (AI) and Rapid Rank Agency (websites):
https://zerotouchai.github.io/upwork-lead-dashboard/

## How it works
- `.github/workflows/refresh.yml` runs every 4 hours (and on demand from the Actions tab), sized to stay under the $5/month Apify free allowance with a $4.50 hard stop.
- `scripts/refresh_data.py` runs the Apify actor `blackfalcondata/upwork-scraper` for three searches
  (AI, Website, and "Hidden" business-problem phrases), then for every job:
  - sorts it into AI or Website by what the title/description is about, and drops off-target gigs,
  - tags a service (voice agent, chatbot, redesign, hosting…) and flags hidden opportunities,
  - folds reposts and near-identical posts into one card,
  - keeps 90 days of leads in `data.json`.
- `index.html` is a static page. Scores, recommendations, bid strategy, profitability and proposal
  drafts are computed in the browser; pipeline status, notes, drafts and settings are saved in your browser.

Search terms and service rules live at the top of `scripts/refresh_data.py`.
Service playbooks (hours, approach, questions) live in `SERVICE_INFO` in `index.html`.

## Setup
Repository secrets (Settings → Secrets and variables → Actions):
- **`APIFY_TOKEN`**: Apify API token.
- **`GMAIL_ADDRESS`** and **`GMAIL_APP_PASSWORD`**: optional; turn on email alerts for new Bid-now leads.
- **`ALERT_TO`**: optional; send alerts to a different inbox (defaults to `GMAIL_ADDRESS`).

## Limits
- Upwork hides its "U.S. only" flag, Connects price, hire rate and jobs-posted count from scrapers.
  "U.S. required" is read from the post text; Connects are a rough estimate; the rest shows as Unknown.
- Competition and win likelihood are estimates. Proposals are drafted, never sent: you review and submit on Upwork.

Check the data rules: `python scripts/test_refresh.py`
