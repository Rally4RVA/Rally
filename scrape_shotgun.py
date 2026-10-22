"""
Rally scraper for venues that sell through Shotgun (shotgun.live): LOSO and Pandora Cafe & House Music.
Each venue page lists its shows with date, time and price. Writes shotgun.json.
"""
import re
import sys
from datetime import date
from rally_common import fmt_time, slug, money, save, event, today_iso, MONTHS

VENUES = [
    {"name": "LOSO", "url": "https://shotgun.live/en/venues/loso", "address": "2727 W Broad St, Richmond, VA"},
    {"name": "Pandora Cafe", "url": "https://shotgun.live/en/venues/pandora-cafe-house-music", "address": "Richmond, VA"},
]
DATE_RE = re.compile(r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.? (\d{1,2})(?:,? (\d{4}))?(?!\d)")
TIME_RE = re.compile(r"\d{1,2}(?::\d{2})?\s?[AP]M", re.I)
PRICE_RE = re.compile(r"\$\s?(\d+(?:\.\d{2})?)")
SKIP = re.compile(r"^(?:Richmond|Sold out|Free|Tickets?|Buy|From|\d{4})$", re.I)


def to_iso(mon, day, year, today):
    m = MONTHS.get(mon[:3].lower())
    try:
        if year:
            return date(int(year), m, int(day)).isoformat()
        d = date(int(today[:4]), m, int(day))
        if d.isoformat() < today:
            d = date(d.year + 1, m, int(day))
        return d.isoformat()
    except (ValueError, TypeError):
        return ""


def parse_card(text, today):
    """One event card's text -> dict, or None. Title is the first line that is not a date, time, price or city."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()]
    flat = " ".join(lines)
    dm = DATE_RE.search(flat)
    if not dm:
        return None
    day = to_iso(dm.group(1), dm.group(2), dm.group(3), today)
    title = ""
    for l in lines:
        if DATE_RE.search(l) or PRICE_RE.search(l) or TIME_RE.fullmatch(l) or SKIP.match(l):
            continue
        title = l
        break
    if not title:
        title = re.split(r"(?:Richmond)?\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d", flat)[0].strip()
    tm = TIME_RE.search(flat[dm.end():])
    pm = PRICE_RE.search(flat)
    sold = bool(re.search(r"sold out", flat, re.I)) and not pm
    price = "Sold out" if sold else (money(pm.group(1)) if pm else "")
    title = re.sub(r"(.{3,}?)\1+", r"\1", title)          # a title printed twice in a row
    title = re.sub(r"\s*\|\s*", ", ", title).strip()
    if not (day and title) or day < today:
        return None
    return dict(title=title, date=day, show_time=fmt_time(tm.group(0)) if tm else "", price=price, free=False)


def run():
    from playwright.sync_api import sync_playwright
    today = today_iso()
    out, ok = [], 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        for v in VENUES:
            try:
                pg.goto(v["url"], wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(6000)
                for _ in range(6):
                    pg.mouse.wheel(0, 5000)
                    pg.wait_for_timeout(600)
                cards = pg.eval_on_selector_all(
                    "a[href*='/events/']", "els => els.map(e => [e.innerText, e.href])")
            except Exception as ex:
                print(v["name"], "failed:", str(ex).splitlines()[0])
                continue
            seen, n = set(), 0
            for text, href in cards:
                if href in seen:
                    continue
                seen.add(href)
                c = parse_card(text, today)
                if not c:
                    continue
                n += 1
                out.append(event(
                    id=f"shotgun-{slug(v['name'])}-{c['date']}-{slug(c['title'])}", title=c["title"], date=c["date"],
                    show_time=c["show_time"], venue=v["name"], url=href, ticket_url=href, kind="m",
                    address=v["address"], price_display=c["price"], free=c["free"]))
                print(" ", v["name"], c["date"], "|", c["title"][:45], "|", c["price"] or "no price", "|", c["show_time"])
            print(f"{v['name']}: {n} shows")
            ok += 1 if n else 0
        b.close()
    if not out or not ok:
        print("No shows came back, so shotgun.json was left alone.")
        sys.exit(1)
    save("shotgun.json", [v["name"] for v in VENUES], out)
    print(f"Saved {len(out)} shows")


if __name__ == "__main__":
    run()
