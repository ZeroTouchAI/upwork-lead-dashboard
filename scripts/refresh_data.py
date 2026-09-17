import os, json, re, base64
from datetime import datetime
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = os.environ["SHEET_ID"]
SA_JSON = os.environ["GCP_SERVICE_ACCOUNT_JSON"]

creds_info = json.loads(SA_JSON)
creds = service_account.Credentials.from_service_account_info(
    creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
service = build("sheets", "v4", credentials=creds)

def clean(s):
    return (s or "").strip()

def fetch_tab(tab_name):
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{tab_name}!A1:L5000"
    ).execute()
    return result.get("values", [])

def build(rows, category):
    out = []
    for r in rows[1:]:
        r = r + [""] * (12 - len(r))
        title, posted, ctype, budget, duration, desc, url, scraped, exp, source, bid, jobid = r[:12]
        out.append({
            "title": clean(title), "posted": clean(posted), "ctype": clean(ctype),
            "budget": clean(budget), "duration": clean(duration), "desc": clean(desc),
            "url": clean(url), "scraped": clean(scraped), "exp": clean(exp),
            "source": clean(source) or "Upwork", "bid": clean(bid), "jobid": clean(jobid),
            "cat": category,
        })
    return out

ai_rows = fetch_tab("AI")
web_rows = fetch_tab("Website")

data = build(ai_rows, "AI") + build(web_rows, "Website")
seen, deduped = set(), []
for r in data:
    key = (r["jobid"], r["cat"])
    if key in seen:
        continue
    seen.add(key)
    deduped.append(r)

ai_list = [r for r in deduped if r["cat"] == "AI"]
web_list = [r for r in deduped if r["cat"] == "Website"]
ai_list.reverse()
web_list.reverse()
final = ai_list + web_list

now_et = datetime.now(ZoneInfo("America/New_York"))
synced = now_et.strftime("%b %-d, %Y \u00b7 %-I:%M %p %Z")

with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"synced": synced, "leads": final}, f, ensure_ascii=False)

print(f"Wrote {len(final)} leads, synced={synced}")
