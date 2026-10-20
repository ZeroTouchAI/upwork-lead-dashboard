# Changelog

## 2026-10-20
- Alert emails redesigned: Project Finder header with lightning bolt, a card per lead (business, service, score, budget, suggested bid, effective rate, client) and a View on Upwork button. Sender shows as "Project Finder".
- Sidebar tools pinned to the bottom: Export CSV, Analytics, Run scraper now (opens the GitHub workflow), Settings & profile.
- "Send a test alert email" option when running the workflow manually from the Actions tab.
- Optional `ALERT_TO` secret sends alert emails to a different inbox than the Gmail account.
- **Email alerts**: each refresh emails new leads the dashboard rates Bid now (score 80+, no red flags), with
  links to the jobs. Needs the `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` secrets.
- Added `CLAUDE.md` (project memory) and this changelog; Python cache files ignored.
- "Ready to bid" card renamed to "Favorites to bid on".
- Compact view: Reject button on every row.
- Applied leads leave the main lists and live under Applied.
- Pipeline simplified to Favorites / Applied / Rejected; Interviewing, Won, Lost and Performance removed.
- Analytics moved to its own page (replaces the Keyboard shortcuts link; shortcuts still work, press `?`).
- "Shortlist" renamed to "Favorites".
- Analytics layout: Key insight full width, three panels below.
- v3.2: AI blue, Website yellow; mixed lists alternate AI and Website.
- v3.1: lead intelligence. Five-part score with Bid now / Review / Low priority / Avoid; client quality summary;
  profitability calculator; bid strategy; Proposal Studio with template drafts and a copyable AI prompt; hidden
  opportunities search; duplicate and repost folding; decision KPIs and Today's best.
- Searches tightened; leads sorted into AI or Website by what the job is about; noise dropped.
- Lightning bolt favicon.
- Make.com Upwork scenarios turned off; the GitHub Action is the only refresh.

## 2026-10-19
- v3.0: new dashboard design and Apify-direct pipeline every 3 hours (no Make, no Google Sheet).

## 2026-09-16 to 2026-10-08
- v2.0–v2.9: original dashboard fed by Make.com → Google Sheet → `data.json`.
