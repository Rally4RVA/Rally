"""
Rally scraper for Cobra Cabana (Eventbrite organizer page).
Writes cobra.json. merge_events.py combines every venue into events.json.

To test on your own computer:
    pip3 install playwright
    python3 -m playwright install chromium
    python3 scrape_cobra.py
"""
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

URL = "https://www.eventbrite.com/o/cobra-cabana-55710974963"
VENUE = "Cobra Cabana"
ADDRESS = "901 W Marshall St, Richmond, VA"
OUT = Path("cobra.json")
TZ = ZoneInfo("America/New_York")

DATE_LINE = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,\s+([A-Z][a-z]{2})[a-z]*\s+(\d{1,2})\s+•\s+(\d{1,2}:\d{2}\s?[AP]M)$"
)
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def clean_title(t):
    t = re.sub(r"^\s*\d{1,2}/\d{1,2}\s*[:\-]\s*", "", t)          # "11/13: " at the start
    t = re.sub(r"\s*@\s*cobra.*$", "", t, flags=re.I)               # "@ Cobra Cabana Nov 14th!!!" at the end
    t = re.sub(r"\s+w/\s*", ", ", t, flags=re.I)                    # "w/" -> comma list
    t = re.sub(r"\s*/\s+", ", ", t)                                 # "A/ B/ C" -> "A, B, C"
    return re.sub(r"\s+", " ", t).strip(" !-")


def infer_date(mon, day, today):
    """Eventbrite shows no year, so use the next time that month/day comes around."""
    y = today.year
    d = date(y, MONTHS[mon], int(day))
    if d < today:
        d = date(y + 1, MONTHS[mon], int(day))
    return d.isoformat()


def price_label(line):
    l = line.strip()
    if re.match(r"^free$", l, re.I):
        return "Free", True
    m = re.match(r"^(?:From\s+)?\$(\d+(?:\.\d{2})?)", l, re.I)
    if m:
        v = float(m.group(1))
        return ("$%d" % v if v == int(v) else "$%.2f" % v) , False
    return "", False


def parse_events(body, links, today):
    lines = [l.strip() for l in body.splitlines()]
    try:
        start = lines.index("Upcoming") + 1
    except ValueError:
        start = 0
    ev_links = [l.split("?")[0] for l in links]
    events = []
    for i in range(start, len(lines)):
        m = DATE_LINE.match(lines[i])
        if not m:
            continue
        j = i - 1
        while j >= 0 and not lines[j]:
            j -= 1
        raw = lines[j]
        price, free = "", False
        for k in range(i + 1, min(i + 8, len(lines))):
            if lines[k].startswith(("Save this event", "Share this event")):
                break
            p, f = price_label(lines[k])
            if p:
                price, free = p, f
                break
        n = len(events)
        url = ev_links[n] if n < len(ev_links) else URL
        events.append({
            "id": "cobra-" + (re.search(r"-(\d{6,})$", url).group(1) if re.search(r"-(\d{6,})$", url) else str(n)),
            "title": clean_title(raw),
            "date": infer_date(m.group(1), m.group(2), today),
            "doors": "",
            "show_time": m.group(3).upper().replace(" ", " "),
            "venue": VENUE,
            "url": url,
            "kind": "m",
            "age": "",
            "address": ADDRESS,
            "price_display": price,
            "free": free,
            "table_price": None,
            "tiers": [],
            "ticket_url": url,
        })
    return [e for e in events if e["date"] >= today.isoformat()]


def scrape(today):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(8000)
        body = pg.inner_text("body")
        links = pg.eval_on_selector_all('a[href*="/e/"]', "els => els.map(e => e.href)")
        b.close()
    seen, uniq = set(), []
    for l in links:
        k = l.split("?")[0]
        if k not in seen:
            seen.add(k)
            uniq.append(l)
    return parse_events(body, uniq, today)


def main():
    today = datetime.now(TZ).date()
    events = scrape(today)
    print(f"Found {len(events)} upcoming Cobra Cabana shows")
    for e in events:
        print(" ", e["date"], e["show_time"], e["title"], "->", e["price_display"] or "no price")
    # An empty list can be real (no shows posted), so save it. A crash keeps the old file.
    OUT.write_text(json.dumps({"updated": datetime.now(TZ).isoformat(timespec="seconds"),
                               "venues": [VENUE], "events": events}, indent=1, ensure_ascii=False),
                   encoding="utf-8")


if __name__ == "__main__":
    main()
