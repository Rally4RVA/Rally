"""Combines each venue's file (camel.json, cobra.json, ...) into the events.json the site reads."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")
FILES = ["camel.json", "cobra.json", "broadberry.json", "gallery5.json", "hardywood.json", "bandito.json", "gettight.json", "manual.json", "mainline.json", "reveler.json", "canalclub.json"]

today = datetime.now(TZ).date().isoformat()
events, venues = [], []
for f in FILES:
    p = Path(f)
    if not p.exists():
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    venues += d.get("venues", [])
    events += [e for e in d.get("events", []) if e["date"] >= today]


def mins(t):
    import re
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", t or "", re.I)
    if not m:
        return 0
    return (int(m.group(1)) % 12 + (12 if m.group(3).upper() == "PM" else 0)) * 60 + int(m.group(2))


import re


def vkey(v):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^the\s+", "", (v or "").lower()))


def bands(title):
    return [re.sub(r"[^a-z0-9]", "", b.lower()) for b in re.split(r",|\bw/\b|\+|&", title or "") if len(re.sub(r"[^a-z0-9]", "", b.lower())) > 2]


def same_show(a, b):
    """Same venue (allowing 'Bandito's' vs 'Bandito's Burrito Lounge'), same day, and a band in common."""
    if a["date"] != b["date"]:
        return False
    ka, kb = vkey(a["venue"]), vkey(b["venue"])
    if not (ka.startswith(kb) or kb.startswith(ka)):
        return False
    ta = re.sub(r"[^a-z0-9]", "", a["title"].lower())
    return any(x in ta for x in bands(b["title"])) or any(x in re.sub(r"[^a-z0-9]", "", b["title"].lower()) for x in bands(a["title"]))


# A hand-entered show that an automatic scraper already found is dropped, so nothing shows twice.
# The scraped one wins, and borrows the price / age from the hand-entered row if it had none.
auto = [e for e in events if not e["id"].startswith("manual-")]
kept = []
for e in events:
    if e["id"].startswith("manual-"):
        twin = next((a for a in auto if same_show(a, e)), None)
        if twin:
            if not twin["price_display"] and e["price_display"]:
                twin["price_display"], twin["free"] = e["price_display"], e["free"]
            if not twin["age"] and e["age"]:
                twin["age"] = e["age"]
            print("  duplicate dropped:", e["date"], e["venue"], "-", e["title"][:40])
            continue
    kept.append(e)
events = kept

# Weekly shows with no calendar (Instagram-only venues). Each upcoming matching day gets a "band on Instagram"
# placeholder, but only when nothing else is listed for that venue on that day, so a real entry replaces it.
from datetime import date as _date, timedelta
RECURRING = [
    {"venue": "Bottoms Up Pizza", "days": [4, 5],   # Python weekday: Monday = 0, Friday = 4, Saturday = 5
     "title": "Live music (see Instagram for the band)", "price": "Free",
     "address": "1700 Dock St, Richmond, VA", "url": "https://www.instagram.com/bottomsuppizza/"},
]
for r in RECURRING:
    for n in range(0, 15):
        d = _date.fromisoformat(today) + timedelta(days=n)
        if d.weekday() not in r["days"]:
            continue
        day = d.isoformat()
        if any(e["date"] == day and (vkey(e["venue"]).startswith(vkey(r["venue"])) or vkey(r["venue"]).startswith(vkey(e["venue"]))) for e in events):
            continue
        events.append({"id": f"recurring-{vkey(r['venue'])}-{day}", "title": r["title"], "date": day, "doors": "", "show_time": "",
                       "venue": r["venue"], "url": r["url"], "kind": "m", "age": "", "address": r["address"],
                       "price_display": r["price"], "free": r["price"].lower().startswith("free"),
                       "table_price": None, "tiers": [], "ticket_url": r["url"]})
        venues.append(r["venue"]) if r["venue"] not in venues else None

events.sort(key=lambda e: (e["date"], mins(e.get("show_time") or e.get("doors"))))
Path("events.json").write_text(json.dumps({
    "updated": datetime.now(TZ).isoformat(timespec="seconds"),
    "venues": venues, "events": events}, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"events.json: {len(events)} shows from {', '.join(venues)}")
