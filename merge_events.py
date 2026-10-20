"""Combines each venue's file (camel.json, cobra.json, ...) into the events.json the site reads."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")
FILES = ["camel.json", "cobra.json", "broadberry.json", "gallery5.json", "hardywood.json", "bandito.json", "gettight.json"]

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


events.sort(key=lambda e: (e["date"], mins(e.get("show_time"))))
Path("events.json").write_text(json.dumps({
    "updated": datetime.now(TZ).isoformat(timespec="seconds"),
    "venues": venues, "events": events}, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"events.json: {len(events)} shows from {', '.join(venues)}")
