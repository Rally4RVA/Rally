"""Small helpers shared by the venue scrapers."""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def today_iso():
    return datetime.now(TZ).date().isoformat()


def fmt_time(t):
    """'6 pm' / '7:30pm' / '6:00 PM' -> '6:00 PM'. Empty if it is not a time."""
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m", t or "", re.I)
    if not m:
        return ""
    return f"{int(m.group(1))}:{m.group(2) or '00'} {m.group(3).upper()}M"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def money(x):
    x = float(x)
    return f"${x:.0f}" if x == int(x) else f"${x:.2f}"


def iso(month_name, day, year):
    return f"{int(year):04d}-{MONTHS[month_name[:3].lower()]:02d}-{int(day):02d}"


def save(path, venues, events):
    Path(path).write_text(json.dumps({
        "updated": datetime.now(TZ).isoformat(timespec="seconds"),
        "venues": venues, "events": events}, indent=1, ensure_ascii=False), encoding="utf-8")


def event(**kw):
    """One show, with every field the site and merge step expect."""
    base = {"id": "", "title": "", "date": "", "doors": "", "show_time": "", "venue": "", "url": "",
            "kind": "m", "age": "", "address": "", "price_display": "", "free": False,
            "table_price": None, "tiers": [], "ticket_url": ""}
    base.update(kw)
    base["ticket_url"] = base["ticket_url"] or base["url"]
    return base
