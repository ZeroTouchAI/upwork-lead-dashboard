"""Pull new Upwork jobs from Apify and merge them into data.json.

  python scripts/refresh_data.py            # scrape (needs APIFY_TOKEN) + merge
  python scripts/refresh_data.py --migrate  # no scrape, just upgrade/prune data.json
"""
import difflib, html, json, os, re, smtplib, sys, urllib.request
from email.message import EmailMessage
from email.utils import formataddr
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
    # Problems clients describe without naming the tech (see PROBLEMS below).
    "Hidden": '"same questions" OR "customer questions" OR "missed calls" OR "appointment requests" OR '
              '"booking requests" OR "copying data" OR "manual data" OR "repetitive tasks" OR "connect our tools" OR '
              '"more leads" OR "outdated website" OR "website is slow"',
}
# Upwork's search matches loose mentions ("eBay help" because the post says "website"), so each job
# is re-sorted by what it is actually about: its title hits WORDS, or failing that its description
# hits PHRASES. AI is checked first. Jobs that match neither category are dropped.
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
                   r"video edit\w*|bookkeep\w*|appointment sett\w*|cold call\w*|tiktok shop|native speakers?|"
                   r"recording|sme|subject matter expert|ai (evaluation|model trainer)|training data|rlhf|annotat\w*|"
                   r"lead lists?|sales (partner|closer|rep\w*)|sdr|account (executive|managers?)|commission[- ]only|100% commission|klaviyo|ugc)\b", re.I)


# Business problems that imply a service, even when the client doesn't name the tech.
# A job matched only by one of these is a "hidden opportunity".
PROBLEMS = [
    ("AI", "AI chatbot & support", r"same (customer )?questions|answer(ing)? (customer |the same )?(questions|inquiries|emails|dms)|customer (support|service) (inbox|tickets|is overwhelming)"),
    ("AI", "Voice AI agent", r"missed (phone )?calls|answer(ing)? (the |our )?phones?|receptionist|after-hours calls"),
    ("AI", "Booking automation", r"appointment (requests|booking|scheduling)|booking requests|schedul(e|ing) (appointments|calls) (manually|by hand)"),
    ("AI", "Workflow automation & integrations", r"copy(ing)? data|manual(ly)? (entering|enter|copying|updat\w+)|double entry|repetitive (tasks|work)|hours (every|each) (day|week) on|spreadsheets? by hand"),
    ("AI", "Workflow automation & integrations", r"connect (several |multiple |our |my |all )?(business )?(tools|apps|systems|platforms)|(tools|apps|systems) (don'?t|do not) talk to each other|sync (data )?between"),
    ("AI", "AI content automation", r"content for (all )?(my|our) (social|platforms|channels)|post(ing)? (daily|consistently) (on|to) social"),
    ("Website", "Conversion & lead capture", r"(website|site) (isn'?t|is not|doesn'?t|does not) (generat|convert|bring|get)\w*|(no|not getting|few) leads from (my|our|the) (website|site)|more leads from (my|our) (website|site)"),
    ("Website", "Website redesign", r"(outdated|old|dated) (website|site)|(website|site) (looks|is) (outdated|old|dated)"),
    ("Website", "Hosting, speed & maintenance", r"(website|site) (is )?(slow|down|hacked|broken|crashing)|hosting (issues|problems)"),
]
PROBLEMS = [(c, s, re.compile(rf"\b({rx})", re.I)) for c, s, rx in PROBLEMS]

# Service label per category, first match wins (title first, then description). The dashboard
# keys its proposal templates and hour estimates off these labels.
SERVICES = {
    "AI": [
        ("Voice AI agent", r"voice (ai|agent|bot|assistant)|receptionist|phone (agent|bot)|ai call\w*|vapi|retell|elevenlabs"),
        ("AI chatbot & support", r"chat ?bots?|customer (support|service) (ai|automation|bot)|support (bot|automation)|faq"),
        ("Booking automation", r"appointment|booking|scheduling"),
        ("AI training & consulting", r"ai (training|course|workshop|consult\w*|tutor|coach\w*|strategy|advisor)|(learn|teach|training|workshop|course|coach\w*|consult\w*)\b.{0,25}\bai\b"),
        ("AI content automation", r"ai (video|image|content|writer|avatar)|content (generation|automation)|image generation|social media automation"),
        ("Workflow automation & integrations", r"n8n|make\.com|zapier|integrat\w*|automat\w*|workflow|api|crm|sync|go ?high ?level|ghl"),
        ("AI app or dashboard", r"dashboard|app\b|saas|platform|mvp|portal|full[- ]?stack"),
        ("AI agent & LLM build", r"agent|llm|gpt|rag|openai|claude|gemini|machine learning|ai"),
    ],
    "Website": [
        ("Hosting, speed & maintenance", r"hosting|maintenance|maintain|migrat\w*|speed|slow|hacked|security|ssl|cpanel|domain|backup|plugins? update"),
        ("Website redesign", r"redesign|re-design|revamp|refresh|moderni[sz]e|rebuild|outdated"),
        ("Conversion & lead capture", r"landing pages?|funnels?|conversion|lead (capture|gen\w*)|cro\b"),
        ("E-commerce store", r"shopify|woocommerce|e-?commerce|online store|magento|store (setup|build)"),
        ("Website fixes & updates", r"\bfix|bug|issue|error|edit|tweak|updates?|changes|add (a |two |new )?(page|section)"),
        ("New website build", r"website|web ?design|web ?develop\w*|wordpress|webflow|wix|squarespace|framer|elementor"),
    ],
}
SERVICES = {c: [(s, re.compile(rf"\b({rx})", re.I)) for s, rx in lst] for c, lst in SERVICES.items()}
DEFAULT_SERVICE = {"AI": "AI agent & LLM build", "Website": "New website build"}


def service_for(cat, l):
    for field in ("title", "desc"):
        for label, rx in SERVICES[cat]:
            if rx.search(l[field]):
                return label
    return DEFAULT_SERVICE[cat]


def classify(l):
    """Returns (cat, service, match) where match is title/desc/problem, or None to drop."""
    if NOISE.search(l["title"]):
        return None
    for key, field in (("words", "title"), ("phrases", "desc")):
        for cat, r in RELEVANT.items():
            if r[key].search(l[field]):
                return cat, service_for(cat, l), field
    for cat, label, rx in PROBLEMS:
        if rx.search(l["title"] + " " + l["desc"]):
            return cat, label, "problem"
    return None


STOP = set("a an and the for to of in on with my our your is are be need needed looking expert developer help".split())


def mark_duplicates(leads):
    """Group reposts and near-identical posts: the oldest is the original, later ones point at it."""
    def words(l):
        return set(re.findall(r"[a-z0-9]+", l["title"].lower())) - STOP
    originals = []
    for l in sorted(leads, key=lambda l: l["posted"]):
        l.pop("dupOf", None)
        l["dups"] = []
        w, d = words(l), re.sub(r"\W+", " ", l["desc"][:400].lower())
        for o in originals:
            ow = o["_w"]
            if w and ow and len(w & ow) / len(w | ow) >= 0.7 and \
                    difflib.SequenceMatcher(None, d, o["_d"]).quick_ratio() >= 0.85 and \
                    difflib.SequenceMatcher(None, d, o["_d"]).ratio() >= 0.8:
                l["dupOf"] = o["id"]
                o["dups"].append(l["id"])
                break
        else:
            l["_w"], l["_d"] = w, d
            originals.append(l)
    for l in leads:
        l.pop("_w", None)
        l.pop("_d", None)
        if not l["dups"]:
            del l["dups"]


COMMON = {
    "maxResults": 80, "maxAgeMinutes": 360,  # 6h window for a 3h schedule; dedupe absorbs the overlap
    "sort": "newest",
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
        "scraped": iso(now), "seen": iso(now), "repost": bool(it.get("isRepost")),
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


# ---------- alerts: email new "Bid now" leads ----------
# Mirrors plan()/score() in index.html with the dashboard's default settings, so an emailed lead
# is one the dashboard also rates Bid now. Keep the two in sync when changing the scoring.
MIN_RATE, FEE, ALERT_MIN_SCORE = 50, 0.10, 80
DASHBOARD = "https://zerotouchai.github.io/upwork-lead-dashboard/"
KEYWORDS = ["ai agent", "chatbot", "voice", "n8n", "make.com", "zapier", "automation", "integration", "dashboard",
            "wordpress", "shopify", "webflow", "redesign", "hosting", "maintenance", "landing page"]
HOURS = {"Voice AI agent": 20, "AI chatbot & support": 15, "Booking automation": 12, "Workflow automation & integrations": 12,
         "AI content automation": 12, "AI training & consulting": 8, "AI app or dashboard": 40, "AI agent & LLM build": 20,
         "Hosting, speed & maintenance": 6, "Website redesign": 25, "Conversion & lead capture": 10, "E-commerce store": 25,
         "Website fixes & updates": 4, "New website build": 25}
US_ONLY = [re.compile(p) for p in (
    r"\b(?:U\.S\.A?\.?|USA?|[Uu]nited [Ss]tates|[Aa]merican)s?[\s\-]*(?:[Oo]nly|[Bb]ased|[Rr]esidents?|[Cc]itizens?)\b",
    r"\b(?:[Oo]nly|[Ee]xclusively)\s+(?:for\s+)?(?:U\.S\.A?\.?|USA?|[Uu]nited [Ss]tates|[Aa]mericans?)\b",
    r"\b[Mm]ust\s+(?:be\s+(?:located|based|residing|living|a\s+resident|a\s+citizen|authorized)|reside|live)[^.\n]{0,30}\b(?:U\.S\.A?\.?|USA?|[Uu]nited [Ss]tates)\b",
    r"\b(?:someone|developer|freelancer|contractor|candidate|designer|engineer|talent|person|individual)\s+(?:who\s+is\s+|that\s+is\s+)?(?:located|based|residing|living)\s+in\s+the\s+(?:U\.S\.A?\.?|USA?|[Uu]nited [Ss]tates)\b",
    r"\b[Aa]uthorized\s+to\s+work\s+in\s+the\s+(?:U\.S\.A?\.?|USA?|[Uu]nited [Ss]tates)\b",
    r"\b[Hh]iring\s+(?:only\s+)?[Aa]mericans?\b")]
SUSPICIOUS = re.compile(r"\b(telegram|whatsapp|signal|skype)\b[^.]{0,40}\b(contact|message|reach|text|add)\b|"
                        r"\b(contact|message|reach|text|add) me\b[^.]{0,40}\b(telegram|whatsapp|signal|skype)\b|"
                        r"\b(outside (of )?upwork|off[- ]platform)\b|\b(unpaid|free (sample|test|trial|work))\b|"
                        r"\b(pay|send) (a |the )?(deposit|fee)\b|\bcrypto(currency)? payment\b", re.I)


def lead_score(l, now):
    hours = HOURS.get(l.get("service"), 20)
    if l["type"] == "hourly":
        c_min, c_max = l["rateMin"] or l["rateMax"], l["rateMax"] or l["rateMin"]
        known = bool(c_max)
        if known and c_max < MIN_RATE:
            r = MIN_RATE
        elif known:
            lo = max(MIN_RATE, round((c_min + c_max) / 2))
            r = round((lo + max(lo, round(c_max))) / 2)
        else:
            r = round((MIN_RATE + round(MIN_RATE * 1.3)) / 2)
        bid = r * hours
    else:
        known = bool(l["budget"])
        bid = round((round(l["budget"] * .85) + round(l["budget"])) / 2) if known else round(MIN_RATE * hours * 1.15)
    size = (l["rateMax"] or 0) * 40 if l["type"] == "hourly" else (l["budget"] or 0)
    cx = 0 if not size else 4 if size < 100 else 8 if size < 500 else 12 if size < 1000 else 16
    net = bid * (1 - FEE) - cx * .15
    eff = net / hours
    text = (l["title"] + " " + l["desc"] + " " + " ".join(l.get("skills") or [])).lower()
    kw = sum(k in text for k in KEYWORDS)
    s = min(25, (15 if l.get("match") == "title" else 13 if l.get("match") == "problem" else 10) + min(10, kw * 4))
    x = eff / MIN_RATE
    s += 12 if not known else 25 if x >= 1.5 else 21 if x >= 1.2 else 17 if x >= 1 else 10 if x >= .7 else 4
    v, sp, rt = l.get("verified"), l.get("spent"), l.get("rating")
    s += (3 if v is None else 6 if v else 0) + (4 if sp is None else 8 if sp >= 10000 else 6 if sp >= 1000 else 4 if sp > 0 else 1) \
        + (3 if not rt else 6 if rt >= 4.7 else 4 if rt >= 4.3 else 2)
    a = l.get("applicants")
    s += 8 if a is None else 15 if a < 5 else 12 if a < 10 else 8 if a < 20 else 4 if a < 50 else 1
    h = (now - datetime.fromisoformat(l["posted"].replace("Z", "+00:00"))).total_seconds() / 3600
    s += (6 if h < 6 else 5 if h < 24 else 3 if h < 72 else 1 if h < 168 else 0) \
        + (4 if l["exp"] in ("Expert", "Intermediate") else 2 if l["exp"] else 3) + (5 if kw >= 2 else 3 if kw else 1)
    text_raw = l["title"] + " . " + l["desc"]
    avoid = any(p.search(text_raw) for p in US_ONLY) or SUSPICIOUS.search(l["desc"]) or (known and (net <= 0 or eff < MIN_RATE * .5))
    return s, bool(avoid), bid, eff


def money(n):
    return f"${n:,.0f}"


def ago(iso_ts, now):
    h = (now - datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))).total_seconds() / 3600
    return f"{max(1, round(h * 60))} min ago" if h < 1 else f"{round(h)} hour{'s' if round(h) != 1 else ''} ago" if h < 24 \
        else "yesterday" if h < 48 else f"{round(h / 24)} days ago"


def alert_html(picks, now, test=False):
    """Branded HTML email. Tables + inline styles only, so it renders the same in Gmail, Outlook and phones."""
    font = "font-family:Inter,'Segoe UI',Helvetica,Arial,sans-serif;"
    cards = []
    for l, s, bid, eff in picks:
        ai = l["cat"] == "AI"
        color, soft, biz = ("#2563eb", "#e6efff", "Zero Touch AI") if ai else ("#b7791f", "#fdf3d0", "Rapid Rank")
        amount = (f"{money(l['rateMin'] or l['rateMax'])}–{money(l['rateMax'])}/hr" if l["rateMax"] else "Not listed") \
            if l["type"] == "hourly" else (money(l["budget"]) + " fixed" if l["budget"] else "Not listed")
        bid_txt = f"~{money(bid / HOURS.get(l['service'], 20))}/hr" if l["type"] == "hourly" else f"~{money(bid)}"
        client = " · ".join(x for x in (
            l.get("country"), f"{money(l['spent'])} spent" if l.get("spent") else None,
            "Payment verified" if l.get("verified") else None,
            f"{l['rating']:.1f}★" if l.get("rating") else None,
            f"{l['applicants']} proposals" if l.get("applicants") is not None else None,
            f"Posted {ago(l['posted'], now)}") if x)
        stat = lambda label, value: (
            f'<td style="padding:10px 12px;background:#f5f6fb;border-radius:8px;{font}" width="33%">'
            f'<div style="font-size:11px;color:#8a90a6;text-transform:uppercase;letter-spacing:.05em">{label}</div>'
            f'<div style="font-size:15px;font-weight:700;color:#141a33;margin-top:2px">{value}</div></td>')
        cards.append(f'''
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e5e7f0;border-left:4px solid {color};border-radius:10px;margin:0 0 14px">
<tr><td style="padding:18px 20px;{font}">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
    <td valign="top" style="{font}">
      <span style="display:inline-block;font-size:11px;font-weight:700;color:{color};background:{soft};padding:3px 10px;border-radius:20px">{biz}</span>
      <span style="display:inline-block;font-size:11px;font-weight:600;color:#5a6178;background:#f1f2f8;padding:3px 10px;border-radius:20px;margin-left:4px">{html.escape(l["service"])}</span>
      <div style="margin-top:10px"><a href="{html.escape(l["url"])}" style="font-size:17px;line-height:1.3;font-weight:700;color:#141a33;text-decoration:none">{html.escape(l["title"])}</a></div>
    </td>
    <td width="70" align="right" valign="top">
      <table role="presentation" cellpadding="0" cellspacing="0"><tr><td align="center" style="width:58px;height:58px;border:4px solid #16a36a;border-radius:50%;{font}">
        <div style="font-size:20px;font-weight:800;color:#141a33;line-height:1">{s}</div>
        <div style="font-size:8px;font-weight:700;letter-spacing:.08em;color:#8a90a6">SCORE</div></td></tr></table>
    </td></tr></table>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="4" style="margin:12px 0 10px"><tr>
    {stat("Client budget", amount)}{stat("Suggested bid", bid_txt)}{stat("Effective rate", f"~{money(eff)}/hr")}
  </tr></table>
  <div style="font-size:13px;color:#5a6178;margin-bottom:14px">{html.escape(client)}</div>
  <a href="{html.escape(l["url"])}" style="display:inline-block;background:#5b4ff5;color:#ffffff;font-size:13px;font-weight:700;padding:10px 18px;border-radius:8px;text-decoration:none">View on Upwork &rarr;</a>
</td></tr></table>''')
    n = len(picks)
    when = now.astimezone(ET).strftime("%b %d, %Y · %I:%M %p %Z").replace(" 0", " ")
    banner = ('<div style="background:#fdf2df;color:#9a5b00;font-size:12px;font-weight:600;padding:8px 12px;border-radius:8px;margin-bottom:14px">'
              'Test email: these are the current best leads, not necessarily new ones.</div>') if test else ""
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="margin:0;padding:0;background:#f5f6fb">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6fb"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%">
  <tr><td style="background:#0e1a3a;border-radius:14px 14px 0 0;padding:22px 26px;{font}">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td width="42" height="42" align="center" valign="middle" style="width:42px;height:42px;background:#5b4ff5;background-image:linear-gradient(135deg,#8b7bff,#3b82f6);border-radius:10px;font-size:22px;line-height:42px">&#9889;</td>
      <td style="padding-left:14px;{font}"><div style="font-size:20px;font-weight:800;color:#ffffff;letter-spacing:-.01em">Project Finder</div>
        <div style="font-size:12px;color:#9aa5c8">Zero Touch AI · Rapid Rank Agency</div></td>
    </tr></table>
  </td></tr>
  <tr><td style="background:#ffffff;padding:22px 26px 6px;{font}">
    {banner}
    <div style="font-size:22px;font-weight:800;color:#141a33">{n} new lead{"s" if n != 1 else ""} rated Bid now</div>
    <div style="font-size:13px;color:#5a6178;margin-top:4px">Scored 80+ for your services, budget and client quality · {when}</div>
  </td></tr>
  <tr><td style="background:#ffffff;padding:16px 26px 10px">{"".join(cards)}</td></tr>
  <tr><td align="center" style="background:#ffffff;border-radius:0 0 14px 14px;padding:6px 26px 26px;{font}">
    <a href="{DASHBOARD}" style="display:inline-block;background:#141a33;color:#ffffff;font-size:14px;font-weight:700;padding:12px 24px;border-radius:9px;text-decoration:none">Open Project Finder</a>
    <div style="font-size:12px;color:#8a90a6;margin-top:10px">Draft a proposal, check the client and track your bids there.</div>
  </td></tr>
  <tr><td align="center" style="padding:16px 26px;{font}"><div style="font-size:11px;color:#8a90a6;line-height:1.5">
    Sent by Project Finder after each scrape when a new lead scores 80+ with no red flags.<br>
    Scores and bids are estimates. Nothing is ever sent to Upwork for you.</div></td></tr>
</table></td></tr></table></body></html>'''


def send_alert(picks, now, test=False):
    user, pw = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pw):
        print(f"{len(picks)} alert-worthy leads; email skipped (GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set)")
        return
    msg = EmailMessage()
    top, n = picks[0][0]["title"], len(picks)
    msg["Subject"] = ("[Test] " if test else "") + f"⚡ {n} new Bid-now lead{'s' if n > 1 else ''}: {top[:60]}"
    msg["From"], msg["To"] = formataddr(("Project Finder", user)), os.environ.get("ALERT_TO") or user  # ALERT_TO: optional other inbox
    msg.set_content("Project Finder: new Upwork leads rated Bid now\n\n" + "\n".join(f"- {l['title']}\n  {l['url']}" for l, *_ in picks)
                    + f"\n\nOpen Project Finder: {DASHBOARD}")
    msg.add_alternative(alert_html(picks, now, test), subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"Emailed {len(picks)} alert(s)")


def main():
    now = datetime.now(timezone.utc)
    with open(DATA, encoding="utf-8") as f:
        old = json.load(f)
    leads = {}
    for r in old.get("leads", []):
        l = from_legacy(r) if "ctype" in r else r
        if l["id"]:
            leads.setdefault(l["id"], l)

    added, new_ids = 0, set()
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
                    new_ids.add(l["id"])
                leads[l["id"]] = l

    cutoff = iso(now - timedelta(days=KEEP_DAYS))
    final = []
    for l in leads.values():
        c = classify(l)
        if c and l["scraped"] >= cutoff:
            l["cat"], l["service"], l["match"] = c
            l.setdefault("seen", l["scraped"])
            final.append(l)
    mark_duplicates(final)
    final.sort(key=lambda l: l["posted"], reverse=True)
    synced = now.astimezone(ET).strftime("%b %d, %Y · %I:%M %p %Z").replace(" 0", " ")
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump({"v": 3, "synced": synced, "leads": final}, f, ensure_ascii=False)
    print(f"{added} new, {len(final)} total, synced={synced}")

    picks, test = [], "--test-alert" in sys.argv  # test: send the current best leads, new or not
    for l in final:
        if (test or l["id"] in new_ids) and "dupOf" not in l:
            s, avoid, bid, eff = lead_score(l, now)
            if s >= ALERT_MIN_SCORE and not avoid:
                picks.append((l, s, bid, eff))
    if picks:
        picks.sort(key=lambda p: -p[1])
        try:
            send_alert(picks[:(3 if test else 10)], now, test)
        except Exception as e:  # never lose the data refresh over an email problem
            print(f"Alert email failed: {e}")


if __name__ == "__main__":
    main()
