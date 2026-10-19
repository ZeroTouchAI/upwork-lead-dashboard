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
