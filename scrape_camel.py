"""
Rally scraper for The Camel (thecamel.org).

Reads every upcoming show, including the ticket prices from the embedded
Opendate checkout, and writes camel.json (merge_events.py combines every venue into events.json).
Runs every morning on GitHub Actions (see .github/workflows/update.yml).

To test on your own computer:
    pip3 install playwright
    python3 -m playwright install chromium
    python3 scrape_camel.py
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://www.thecamel.org"
VENUE = "The Camel"
OUT = Path("camel.json")
MIN_EVENTS = 10          # if fewer shows than this come back, something broke: keep the old file
TZ = ZoneInfo("America/New_York")
PAUSE = 0.5
DEBUG_LIMIT = 5

DATE_RE = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})")
TIME_RE = r"(\d{1,2}:\d{2}\s?[ap]m)"
FEE_RE = re.compile(
    r"^\$(\d+(?:\.\d{2})?)\s*\(\s*\$(\d+(?:\.\d{2})?)\s*\+\s*\$(\d+(?:\.\d{2})?)\s*fee\s*\)$",
    re.I,
)
SIMPLE_RE = re.compile(r"^\$(\d+(?:\.\d{2})?)$")
STATUS_RE = re.compile(r"sale|sold|ended|unavailable|closed", re.I)
AGE_RE = re.compile(r"^(all ages|\d{2}\+)$", re.I)
ADDR_RE = re.compile(r"\d+ .*Richmond, VA", re.I)

# Shows that are not live music get a small "not a gig" tag and are hidden by "Music only".
NOT_MUSIC = (
    "spellslingers", "camel comedy", "drag brunch", "drag night", "live spooky",
    "vice live", "scrappy hour", "trivia", "bingo",
)
SKIP_TITLES = ("closed for private",)


# ---------------------------------------------------------------- price logic

def parse_tiers(text):
    """Pull ticket tiers (name, price, fee, status) out of the Opendate checkout text."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    tiers, seen = [], set()
    for i, line in enumerate(lines):
        m = FEE_RE.match(line)
        if m:
            total, base, fee = (float(x) for x in m.groups())
        else:
            m2 = SIMPLE_RE.match(line)
            if not m2:
                continue
            total = base = float(m2.group(1))
            fee = 0.0
        if i == 0:
            continue
        status = ""
        if i + 1 < len(lines) and len(lines[i + 1]) < 40 and STATUS_RE.search(lines[i + 1]):
            status = lines[i + 1]
        key = (lines[i - 1], base, status)
        if key in seen:            # table-reservation lists repeat the same line many times
            continue
        seen.add(key)
        tiers.append({"name": lines[i - 1], "base": base, "fee": fee, "total": total, "status": status})
    return tiers


def money(x):
    return f"${x:.0f}" if x == int(x) else f"${x:.2f}"


def is_door(name):
    n = name.lower()
    return "door" in n or "day of" in n or "day-of" in n


def available(tier):
    """On sale now, or a later sale (like day-of tickets) that has not opened yet."""
    s = tier["status"].lower()
    return (not s) or s.startswith("sales start")


def price_display(tiers):
    """Short label, e.g. '$10 adv · $12 door', '$12 door', '$5–$15', '$15'."""
    if not tiers:
        return ""
    open_t = [t for t in tiers if available(t)]
    if not open_t:
        return "Sold out" if any("sold" in t["status"].lower() for t in tiers) else "Sale ended"
    door = [t for t in open_t if is_door(t["name"])]
    other = [t for t in open_t if not is_door(t["name"])]
    parts = []
    if other:
        lo = min(t["base"] for t in other)
        hi = max(t["base"] for t in other)
        s = money(lo) if lo == hi else money(lo) + "–" + money(hi)
        if door:
            s += " adv"
        parts.append(s)
    if door:
        parts.append(money(min(t["base"] for t in door)) + " door")
    return " · ".join(parts)


def free_label(text):
    """'' if the page is not a free show. Otherwise 'Free' plus any extra, e.g. 'Free · $15 tables'."""
    m = re.search(r"(?m)^\s*FREE\b(.*)$", text)
    if not m and not re.search(r"\bFree!", text):
        return ""
    rest = m.group(1) if m else ""
    t = re.search(r"\$\s?(\d+(?:\.\d{2})?)\s*table", rest, re.I)
    if t:
        return f"Free · ${float(t.group(1)):.0f} tables"
    u = re.search(r"\$\s?(\d+(?:\.\d{2})?)\s*if under\s*(\d+)", rest, re.I)
    if u:
        return f"Free · ${float(u.group(1)):.0f} under {u.group(2)}"
    return "Free"


def kind_of(title):
    return "o" if title.lower().startswith(NOT_MUSIC) or any(k in title.lower() for k in NOT_MUSIC) else "m"


def minutes(t):
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", t or "", re.I)
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "PM" else 0)
    return h * 60 + int(m.group(2))


def clean_doors(doors, show):
    """Some pages list doors after the show start. That is a typo on their side, so drop it."""
    a, b = minutes(doors), minutes(show)
    return "" if a is not None and b is not None and a > b else doors


# ------------------------------------------------------------------- browsing

def opendate_text(page, wait_s=14):
    """Text of the embedded Opendate checkout on the show page."""
    end = time.time() + wait_s
    last = ""
    while time.time() < end:
        for f in page.frames:
            if "app.opendate.io" in f.url:
                try:
                    t = f.inner_text("body", timeout=2000)
                except Exception:
                    t = ""
                if "$" in t or "Free" in t or "Sold Out" in t or "Powered by" in t:
                    return f.url, t
                last = t
        time.sleep(0.5)
    return "", last


def find_show_links(page):
    page.goto(f"{BASE}/shows", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    links = []
    for h in hrefs:
        if not h:
            continue
        full = h if h.startswith("http") else BASE + h
        if re.match(rf"^{re.escape(BASE)}/shows/[^/#?]+$", full) and full not in links:
            links.append(full)
    return links


def parse_show(page, url, today, debug_dir, counter):
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1500)
    text = page.inner_text("body")

    title = ""
    try:
        title = page.inner_text("h1", timeout=3000).strip()
    except Exception:
        pass
    if title.lower().startswith(SKIP_TITLES):
        return None

    iso = ""
    m = DATE_RE.search(text)
    if m:
        try:
            iso = datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
        except ValueError:
            pass
    if not iso or iso < today:
        return None

    doors = re.search(r"Doors:\s*" + TIME_RE, text, re.I)
    show = re.search(r"Show:\s*" + TIME_RE, text, re.I)
    show_time = show.group(1).upper() if show else ""
    doors_time = clean_doors(doors.group(1).upper() if doors else "", show_time)

    free = free_label(text)
    tm = re.search(r"\$\s?(\d+(?:\.\d{2})?)\s*Table", text, re.I)

    frame_url, od = opendate_text(page)
    tiers = parse_tiers(od)
    if not tiers and not free:
        page.reload(wait_until="domcontentloaded", timeout=45000)   # the checkout sometimes loads late
        page.wait_for_timeout(1500)
        frame_url, od = opendate_text(page)
        tiers = parse_tiers(od)
    lines = [l.strip() for l in od.splitlines() if l.strip()]

    ticket_url = frame_url
    if not ticket_url:
        for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))"):
            if h and any(k in h for k in ("hive.co", "etix.com", "opendate.io")):
                ticket_url = h
                break

    if counter[0] < DEBUG_LIMIT and not tiers and not free:
        Path(debug_dir).mkdir(exist_ok=True)
        (Path(debug_dir) / f"notiers_{counter[0]}.txt").write_text(
            f"URL: {url}\nFRAME: {frame_url}\n\n{od}", encoding="utf-8")
        counter[0] += 1

    return {
        "id": url.rsplit("/", 1)[-1],
        "title": title,
        "date": iso,
        "doors": doors_time,
        "show_time": show_time,
        "venue": VENUE,
        "url": url,
        "kind": kind_of(title),
        "age": next((l for l in lines if AGE_RE.match(l)), ""),
        "address": next((l for l in lines if ADDR_RE.search(l)), ""),
        "price_display": free or price_display(tiers),
        "free": bool(free),
        "table_price": float(tm.group(1)) if tm else None,
        "tiers": tiers,
        "ticket_url": ticket_url,
    }


def scrape():
    from playwright.sync_api import sync_playwright   # imported here so the price logic above can be tested without it

    today = datetime.now(TZ).date().isoformat()
    events, counter = [], [0]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        links = find_show_links(page)
        print(f"Found {len(links)} show pages")
        for i, url in enumerate(links, 1):
            ev, err = None, ""
            for _ in range(3):
                try:
                    ev = parse_show(page, url, today, "debug", counter)
                    err = ""
                    break
                except Exception as e:
                    err = str(e).splitlines()[0]
                    time.sleep(2)
            if err:
                print(f"[{i}/{len(links)}] FAILED {url}: {err}")
                continue
            if ev is None:
                continue
            events.append(ev)
            print(f"[{i}/{len(links)}] {ev['date']} {ev['title']} -> {ev['price_display'] or 'no price found'}")
            time.sleep(PAUSE)
        browser.close()
    events.sort(key=lambda e: (e["date"], minutes(e["show_time"]) or 0))
    return events


def main():
    events = scrape()
    if len(events) < MIN_EVENTS:
        print(f"Only {len(events)} upcoming shows came back, so camel.json was left alone.")
        sys.exit(1)
    data = {
        "updated": datetime.now(TZ).isoformat(timespec="seconds"),
        "venues": [VENUE],
        "events": events,
    }
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    missing = sum(1 for e in events if not e["price_display"])
    print(f"Saved {len(events)} upcoming shows to {OUT} ({missing} without a price)")


if __name__ == "__main__":
    main()
