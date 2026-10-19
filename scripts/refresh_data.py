"""Pull new Upwork jobs from Apify and merge them into data.json.

  python scripts/refresh_data.py            # scrape (needs APIFY_TOKEN) + merge
  python scripts/refresh_data.py --migrate  # no scrape, just upgrade/prune data.json
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ACTOR = "blackfalcondata~upwork-scraper"
DATA = os.path.join(os.path.dirname(__file__), "..", "data.json")
ET = ZoneInfo("America/Toronto")
KEEP_DAYS = 90
SEARCHES = {
    "AI": '"AI automation" OR "AI agent" OR chatbot OR n8n OR "make.com" OR zapier OR openai OR chatgpt OR llm OR rag OR "voice agent"',
    "Website": 'website OR wordpress OR shopify OR webflow OR wix OR "landing page" OR "web design"',
}
COMMON = {
    "maxResults": 50, "maxAgeMinutes": 1440, "sort": "newest",
    "incrementalMode": True, "descriptionFormat": "text", "descriptionMaxLength": 3000,
}


def scrape(query):
    req = urllib.request.Request(
        f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items?timeout=280",
        data=json.dumps({**COMMON, "query": query}).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['APIFY_TOKEN']}"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def norm_exp(e):
    e = (e or "").lower()
    return "Expert" if "expert" in e else "Intermediate" if "intermediate" in e else "Entry Level" if "entry" in e else ""


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_apify(it, cat, now):
    jtype = (it.get("jobType") or "").lower()
    skills = [s if isinstance(s, str) else (s.get("name") or s.get("prefLabel") or "") for s in it.get("skills") or []]
    return {
        "id": str(it.get("jobId") or it.get("url") or ""), "cat": cat,
        "title": (it.get("title") or "").strip(),
        "desc": (it.get("description") or it.get("descriptionText") or "").strip(),
        "url": it.get("url") or "",
        "type": "hourly" if "hour" in jtype else "fixed" if "fix" in jtype else "",
        "rateMin": num(it.get("hourlyBudgetMin")), "rateMax": num(it.get("hourlyBudgetMax")),
        "budget": num(it.get("budgetAmount")),
        "exp": norm_exp(it.get("experienceLevel")),
        "duration": it.get("engagementDuration") or "", "workload": it.get("engagementType") or "",
        "applicants": it.get("totalApplicants"),
        "country": it.get("clientCountry") or "", "cc": it.get("clientCountryCode") or "",
        "spent": num(it.get("clientTotalSpent")), "verified": it.get("clientPaymentVerified"),
        "rating": num(it.get("clientRating")), "reviews": it.get("clientReviewCount"),
        "skills": [s for s in skills if s],
        "posted": it.get("publishTime") or it.get("createTime") or iso(now),
        "scraped": iso(now),
    }


REL = re.compile(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago")


def from_legacy(r):
    """v2 sheet rows -> v3 shape. Posted time is estimated from 'Posted 4 days ago' + scrape date."""
    try:
        scraped = datetime.strptime(r["scraped"].strip(), "%a, %b %d, %Y").replace(hour=7, minute=30, tzinfo=ET)
    except ValueError:
        scraped = datetime.now(ET)
    p = r.get("posted", "").lower()
    m = REL.search(p)
    if m:
        n, unit = int(m[1]), m[2]
        back = timedelta(minutes=n) if unit == "minute" else timedelta(hours=n) if unit == "hour" else \
            timedelta(days=n * {"day": 1, "week": 7, "month": 30}[unit])
    else:
        back = timedelta(days=1 if "yesterday" in p else 7 if "last week" in p else 0)
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", r.get("budget", ""))]
    hourly = "hourly" in r.get("ctype", "").lower()
    dur, _, work = r.get("duration", "").partition(", ")
    return {
        "id": r.get("jobid") or r.get("url", ""), "cat": r["cat"], "title": r["title"], "desc": r["desc"], "url": r["url"],
        "type": "hourly" if hourly else "fixed" if "fixed" in r.get("ctype", "").lower() else "",
        "rateMin": nums[0] if hourly and nums else None, "rateMax": nums[-1] if hourly and nums else None,
        "budget": nums[-1] if not hourly and nums else None,
        "exp": norm_exp(r.get("exp")), "duration": dur, "workload": work, "applicants": None,
        "country": "", "cc": "", "spent": None, "verified": None, "rating": None, "reviews": None, "skills": [],
        "posted": iso(scraped - back), "scraped": iso(scraped),
    }


def main():
    now = datetime.now(timezone.utc)
    with open(DATA, encoding="utf-8") as f:
        old = json.load(f)
    leads = {}
    for r in old.get("leads", []):
        l = from_legacy(r) if "ctype" in r else r
        if l["id"]:
            leads.setdefault(l["id"], l)

    added = 0
    if "--migrate" not in sys.argv:
        for cat, q in SEARCHES.items():
            items = scrape(q)
            print(f"{cat}: {len(items)} jobs from Apify")
            for it in items:
                l = from_apify(it, cat, now)
                if not l["id"]:
                    continue
                if l["id"] in leads:  # refresh live fields, keep first-seen category + scrape time
                    keep = leads[l["id"]]
                    l.update(cat=keep["cat"], scraped=keep["scraped"])
                else:
                    added += 1
                leads[l["id"]] = l

    cutoff = iso(now - timedelta(days=KEEP_DAYS))
    final = sorted((l for l in leads.values() if l["scraped"] >= cutoff), key=lambda l: l["posted"], reverse=True)
    synced = now.astimezone(ET).strftime("%b %d, %Y · %I:%M %p %Z").replace(" 0", " ")
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump({"v": 3, "synced": synced, "leads": final}, f, ensure_ascii=False)
    print(f"{added} new, {len(final)} total, synced={synced}")


if __name__ == "__main__":
    main()
