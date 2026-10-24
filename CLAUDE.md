# Project notes for Claude

Upwork lead intelligence dashboard for two businesses owned by the same person:
- **Zero Touch AI Automation**: AI work (category `AI`, shown in **blue**).
- **Rapid Rank Agency**: websites, hosting, maintenance (category `Website`, shown in **yellow**).

Live site: https://zerotouchai.github.io/upwork-lead-dashboard/ (GitHub Pages from `main`).

## Working rules
- **Every change gets committed and pushed to `main`** as soon as it's verified. The owner wants GitHub to hold the
  full history. Add a line to `CHANGELOG.md` for each user-facing change.
- Pull with `git pull --rebase --autostash` before committing: the bot commits `data.json` every 3 hours.
- Keep it free: no paid AI APIs. AI features use templates in the page plus a "Copy AI prompt" button the owner
  pastes into their own ChatGPT/Claude.
- Never automate bidding, messaging or proposal submission on Upwork. The dashboard drafts; the owner submits.
- The repo is public: never commit emails, tokens or passwords. They go in GitHub Actions secrets.

## Architecture
- `scripts/refresh_data.py`: runs Apify actor `blackfalcondata/upwork-scraper` (searches: AI, Website, Hidden),
  classifies each job (title words → description phrases → business-problem phrases), drops noise, tags a service,
  folds duplicates, keeps 90 days, writes `data.json`, and emails new "Bid now" leads via Gmail.
- `index.html`: single static page, vanilla JS, no build step. Scoring (`plan()`/`score()`), recommendations,
  client intel, bid strategy, proposal drafts (`SERVICE_INFO`), analytics. User state lives in localStorage.
- `lead_score()` in the Python script **mirrors** `plan()`/`score()` in `index.html` with default settings, so emailed
  leads match the dashboard's Bid now. Change both together.
- `scripts/test_refresh.py`: run after editing the script.
- Apify bills per job returned: runs use `lastScrape` in data.json to look back only since the last good run,
  capped by `MAX_RESULTS`. Apify refusals set `scrapeError` (dashboard banner) instead of failing the workflow.
- Secrets: `APIFY_TOKEN`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`.

## Owner preferences
- Canadian freelancer: hide U.S.-only jobs (detected from post text; Upwork hides the real flag from scrapers).
- Mixed lists alternate AI and Website.
- Pipeline is only Favorites → Applied (or Rejected). Applied leads leave the main lists.
- Analytics lives on its own page.
- "Can't apply" remembers clients in localStorage (`pf_blocked`) and matches later jobs by exact footprint
  (country, total spend, reviews, rating) because Upwork gives no client ID. Looser matching gave false hits.
- Email links: `?lead=<id>` (open that lead), `?proposal=<id>` (open its draft), `?fav=<id>` (favorite it).
  Favorites and drafts are per browser (localStorage).
