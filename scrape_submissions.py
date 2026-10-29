"""
Rally: shows that bands and venues sent in through the "Submit a show" page.
Only shows you approved in Supabase (status = 'approved') come through here. Writes submissions.json.
No password is needed: the database hands out approved shows only, never emails or notes.
"""
import json
import sys
import urllib.request
from rally_common import fmt_time, save, event, today_iso

SUPABASE_URL = "https://ojaxnqxbrqssyykxvwjj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9qYXhucXhicnFzc3l5a3h2d2pqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI0MzI4NDYsImV4cCI6MjEwODAwODg0Nn0.r38T5DjBQqdTnt7DK2M1fFCMPrsv2lVsrO__dqkesSs"


def fetch_rows():
    req = urllib.request.Request(
        SUPABASE_URL + "/rest/v1/rpc/approved_shows", data=b"{}", method="POST",
        headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.loads(f.read().decode("utf-8"))


def to_events(rows, today):
    out = []
    for r in rows:
        day = (r.get("show_date") or "")[:10]
        if not (r.get("title") and r.get("venue") and day) or day < today:
            continue
        link = r.get("link") or ""
        price = (r.get("price") or "").strip()
        out.append(event(
            id="manual-sub-" + (r.get("id") or "")[:8], title=r["title"].strip(), date=day,
            doors=fmt_time(r.get("doors")), show_time=fmt_time(r.get("show_time")),
            venue=r["venue"].strip(), url=link if link.startswith("http") else "", age=(r.get("age") or "").strip(),
            price_display=price, free=price.lower().startswith("free")))
    return out


def main():
    try:
        rows = fetch_rows()
    except Exception as e:
        print("Couldn't read submissions, so submissions.json was left alone:", e)
        sys.exit(1)
    events = to_events(rows, today_iso())
    save("submissions.json", sorted({e["venue"] for e in events}), events)
    print(f"Saved {len(events)} approved submitted shows")


if __name__ == "__main__":
    main()
