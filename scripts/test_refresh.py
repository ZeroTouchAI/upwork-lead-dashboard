# Run: python scripts/test_refresh.py
import importlib.util, sys
from datetime import datetime, timezone
spec = importlib.util.spec_from_file_location("r", __file__.replace("test_refresh.py", "refresh_data.py")); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
now = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)
l = r.from_apify({"jobId": "~0123", "title": " Build n8n agent ", "jobType": "HOURLY", "experienceLevel": "EXPERT",
    "hourlyBudgetMin": 40, "hourlyBudgetMax": "75", "clientCountry": "Canada", "clientCountryCode": "CA",
    "clientTotalSpent": 12000, "clientPaymentVerified": True, "totalApplicants": 3,
    "skills": [{"name": "n8n"}, "OpenAI API"], "publishTime": "2026-10-19T18:00:00Z", "description": "x"}, "AI", now)
assert l["id"] == "~0123" and l["title"] == "Build n8n agent" and l["type"] == "hourly"
assert l["exp"] == "Expert" and l["rateMax"] == 75.0 and l["skills"] == ["n8n", "OpenAI API"] and l["cc"] == "CA"
leg = r.from_legacy({"title": "t", "desc": "d", "url": "u", "cat": "AI", "jobid": "9", "ctype": "Hourly: $25.00 - $40.00",
    "budget": "$25.00 - $40.00", "duration": "1 to 3 months, Less than 30 hrs/week", "exp": "jsn_Intermediate_206",
    "posted": "Posted 2 days ago", "scraped": "Sun, Oct 18, 2026 "})
assert leg["exp"] == "Intermediate" and (leg["rateMin"], leg["rateMax"]) == (25.0, 40.0) and leg["workload"] == "Less than 30 hrs/week"
assert leg["posted"] < leg["scraped"] and leg["posted"].startswith("2026-10-16"), leg["posted"]
print("ok")
c = lambda title, desc="": r.classify({"title": title, "desc": desc})
assert c("EBay help", "update my website") is None
c = lambda title, desc="": (r.classify({"title": title, "desc": desc}) or [None])[0]
assert c("AI Trainer for Live Zoom Workshops for Business Teams") == "AI"
assert c("Full-Stack Developer Needed - Quote for Complete Website, iOS & Android App") == "Website"
assert c("Website Developer + SEO + Google Ads") == "Website"
assert c("WordPress AI chatbot plugin") == "AI"
assert c("Internal Medicine SME - AI Evaluation") is None
assert c("Help with my business", "We need to redesign our website") == "Website"
print("classify ok")
assert r.classify({"title": "Help for my dental clinic", "desc": "We keep getting missed calls after hours"}) == ("AI", "Voice AI agent", "problem")
assert r.classify({"title": "Shopify store setup", "desc": ""})[1] == "E-commerce store"
a = {"id": "1", "title": "Build WordPress site for bakery", "desc": "Need a 5 page WordPress site for my bakery with menu and contact form.", "posted": "2026-10-01"}
b = dict(a, id="2", posted="2026-10-03")
z = {"id": "3", "title": "Voice agent for clinic", "desc": "Something else entirely", "posted": "2026-10-02"}
r.mark_duplicates([a, b, z])
assert a["dups"] == ["2"] and b["dupOf"] == "1" and "dupOf" not in z and "dups" not in z
print("services + duplicates ok")
