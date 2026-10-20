"""
Rally: shows you type in by hand (for venues that only post flyers on Instagram).
Reads a Google Sheet that is published as CSV and writes manual.json.

Sheet columns (row 1 is the header): venue, title, date, show_time, doors, price, age, link, address, music
  date:  10/24/2026, 10/24 or Oct 24, 2026 all work
  price: anything you type is shown as is ("Free", "$10", "$10 adv / $15 door")
  music: leave blank for a gig, type "no" for something that is not live music
"""
import csv
import io
import re
import sys
import urllib.request
from datetime import datetime, date
from rally_common import fmt_time, iso, slug, save, event, today_iso, TZ

SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTwkph-aeHkrW7tn5SKxNovNKxZJyiB93c-E8pFVIjT5ZbEkR0Li4nURKj4G7Yl6oTJt92fsHQhwTqo/pub?gid=368460146&single=true&output=csv"


def parse_date(s, today):
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", s)
    if m:
        y = int(m.group(3)) if m.group(3) else None
        if y is not None and y < 100:
            y += 2000
        return _fix(int(m.group(1)), int(m.group(2)), y, today)
    m = re.fullmatch(r"(?:[A-Za-z]+,?\s+)?([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?", s)
    if m:
        from rally_common import MONTHS
        mon = MONTHS.get(m.group(1).lower())
        if mon:
            return _fix(mon, int(m.group(2)), int(m.group(3)) if m.group(3) else None, today)
    return ""


def _fix(mon, day, year, today):
    try:
        if year is None:
            d = date(int(today[:4]), mon, day)
            if d.isoformat() < today:
                d = date(d.year + 1, mon, day)
            return d.isoformat()
        return date(year, mon, day).isoformat()
    except ValueError:
        return ""


def parse_rows(text, today):
    rows = csv.DictReader(io.StringIO(text))
    out, seen = [], set()
    for r in rows:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        venue, title = r.get("venue", ""), r.get("title", "")
        day = parse_date(r.get("date", ""), today)
        if not (venue and title and day) or day < today:
            continue
        price = r.get("price", "")
        eid = f"manual-{slug(venue)}-{day}-{slug(title)}"
        if eid in seen:
            continue
        seen.add(eid)
        link = r.get("link", "")
        out.append(event(
            id=eid, title=re.sub(r"\s+w/\s+", ", ", title, flags=re.I), date=day,
            doors=fmt_time(r.get("doors", "")), show_time=fmt_time(r.get("show_time", "")),
            venue=venue, url=link if link.startswith("http") else "", age=r.get("age", ""),
            address=r.get("address", ""), price_display=price, free=price.lower().startswith("free"),
            kind="o" if r.get("music", "").lower() in ("no", "n", "false", "0") else "m"))
    return out


def main():
    if not SHEET_URL:
        print("No sheet link set yet, so manual.json was left alone.")
        return
    today = today_iso()
    with urllib.request.urlopen(SHEET_URL, timeout=30) as f:
        text = f.read().decode("utf-8-sig")
    if text.lstrip().lower().startswith("<"):
        print("The sheet link returned a web page, not CSV. Check that it is published as CSV.")
        sys.exit(1)
    events = parse_rows(text, today)
    if not events:
        print("The sheet had no upcoming shows in it, so manual.json was left alone.")
        return
    save("manual.json", sorted({e["venue"] for e in events}), events)
    print(f"Saved {len(events)} hand-entered shows from {len({e['venue'] for e in events})} venues")


if __name__ == "__main__":
    main()
