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
# Upwork search per category (Upwork matches ALL words; OR joins alternatives).
SEARCHES = {
    "AI": 'AI OR "artificial intelligence" OR chatbot OR chatgpt OR openai OR claude OR gemini OR llm OR gpt OR '
          '"machine learning" OR "voice agent" OR "AI agent" OR n8n OR "make.com" OR zapier',
    "Website": 'website OR "web design" OR "web developer" OR wordpress OR shopify OR webflow OR wix OR squarespace OR '
               '"landing page" OR redesign OR "web hosting" OR "website maintenance"',
}
# A job is kept only if its title or skills hit WORDS, or its description hits PHRASES. Upwork's
# search also matches loose mentions ("eBay help" because the post says "website"), so we re-check.
RELEVANT = {
    "AI": {
        "words": re.compile(r"\b(ai|a\.i\.|artificial intelligence|chat ?bots?|chatgpt|gpt|openai|claude|gemini|llms?|"
                            r"machine learning|ml|deep learning|nlp|computer vision|agents?|agentic|rag|prompt|voice|"
                            r"n8n|make\.com|zapier|automation|automate|mcp|openrouter|comfyui|stable diffusion|midjourney|image generation|speech|tts)\b", re.I),
        "phrases": re.compile(r"\b(ai (agent|assistant|tool|app|model|automation|integration|chatbot|voice|tutor|course|training|consult\w*)|"
                              r"artificial intelligence|chatbot|chatgpt|openai|llm|machine learning|voice (ai|agent)|"
                              r"learn (to use )?ai|ai-powered)\b", re.I),
    },
    "Website": {
        "words": re.compile(r"\b(web ?sites?|web ?design\w*|web ?develop\w*|web ?pages?|wordpress|woocommerce|shopify|"
                            r"webflow|wix|squarespace|framer|elementor|divi|landing pages?|redesign|re-design|hosting|"
                            r"web|domain|cpanel|magento|funnels?|go ?high ?level|ghl|site (maintenance|migration|speed|fix|update)|front ?end|html|css)\b", re.I),
        "phrases": re.compile(r"\b((new|build|redesign|update|upgrade|fix|maintain|migrate|host) (a |my |our |the )?(web ?site|site)|"
                              r"web ?site (redesign|maintenance|hosting|update|upgrade|migration|build)|web hosting|"
                              r"wordpress (site|website|developer)|shopify (store|site|developer)|landing page)\b", re.I),
    },
}
# Never wanted, whatever the category (checked against the title only).
NOISE = re.compile(r"\b(ebay|amazon (seller|listing|fba|store)|etsy|data entry|virtual assistant|back ?links?|"
                   r"video edit\w*|bookkeep\w*|appointment sett\w*|cold call\w*|tiktok shop)\b", re.I)


def relevant(l):
    if NOISE.search(l["title"]):
        return False
    r = RELEVANT.get(l["cat"])
    head = l["title"] + " " + " ".join(l.get("skills") or [])
    return not r or bool(r["words"].search(head) or r["phrases"].search(l["desc"]))


COMMON = {
    "maxResults": 80, "maxAgeMinutes": 1440, "sort": "newest",
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
    final = sorted((l for l in leads.values() if l["scraped"] >= cutoff and relevant(l)), key=lambda l: l["posted"], reverse=True)
    synced = now.astimezone(ET).strftime("%b %d, %Y · %I:%M %p %Z").replace(" 0", " ")
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump({"v": 3, "synced": synced, "leads": final}, f, ensure_ascii=False)
    print(f"{added} new, {len(final)} total, synced={synced}")


if __name__ == "__main__":
    main()
