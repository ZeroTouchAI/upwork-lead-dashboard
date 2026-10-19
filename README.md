# upwork-lead-dashboard
Personal dashboard of Upwork AI &amp; website project leads: https://zerotouchai.github.io/upwork-lead-dashboard/

## How it works
- `.github/workflows/refresh.yml` runs every 3 hours (and on demand from the Actions tab).
- `scripts/refresh_data.py` runs the Apify actor `blackfalcondata/upwork-scraper` once for AI and once for Website,
  merges new jobs into `data.json` (deduped by job ID, pruned after 90 days) and commits it.
- `index.html` is a static page that reads `data.json`. Pipeline status, notes and settings are saved in your browser.

Search terms live in `SEARCHES` at the top of `scripts/refresh_data.py`.

## Setup
Add a repository secret **`APIFY_TOKEN`** (Settings → Secrets and variables → Actions) with your Apify API token.

## Limits
- Upwork hides its "U.S. only" flag and the Connects price from scrapers. "U.S. required" is detected from the post
  text, and Connects are a rough estimate from job size.

Check the data mapping: `python scripts/test_refresh.py`
