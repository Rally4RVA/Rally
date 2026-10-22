"""
Rally scraper for LOSO and Pandora Cafe & House Music. Both sell through Shotgun.
LOSO's own calendar page (losorichmond.com/calendar) shows each show as a card:
    Title / LOSO / "Oct 23 | 9:00 PM  $22.70" / genre tags
Pandora Cafe's Shotgun page uses the same cards. The scraper reads the visible text of the page (and any embedded
frames), so it does not depend on the page's hidden structure. Writes shotgun.json.
"""
import re
import sys
from datetime import date
from rally_common import fmt_time, slug, money, save, event, today_iso, MONTHS

VENUES = [
    {"name": "LOSO", "urls": ["https://losorichmond.com/calendar", "https://shotgun.live/en/venues/loso"],
     "address": "2727 W Broad St, Richmond, VA", "names": ["loso"]},
    {"name": "Pandora Cafe", "urls": ["https://shotgun.live/en/venues/pandora-cafe-house-music"],
     "address": "Richmond, VA", "names": ["richmond", "pandora cafe", "pandora café"]},
]
DATE_LINE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{1,2})(?:,? (\d{4}))?\s*\|\s*(\d{1,2}(?::\d{2})?\s?[AP]M)\s*(\$\s?\d+(?:\.\d{2})?)?\s*$", re.I)
PRICE_LINE = re.compile(r"^\$\s?(\d+(?:\.\d{2})?)$")
TAG_LINE = re.compile(r"^(?:\+\d+|[A-Z0-9&/ \-]{3,40})$")   # genre chips are ALL CAPS, e.g. "DETROIT TECHNO", "+1"


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


def parse_text(body, today, venue_names):
    """Cards from page text. Returns a list of dicts in page order."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in body.splitlines() if l.strip()]
    out = []
    for i, l in enumerate(lines):
        m = DATE_LINE.match(l)
        if not m:
            continue
        price = m.group(5) or ""
        if not price and i + 1 < len(lines) and PRICE_LINE.match(lines[i + 1]):
            price = lines[i + 1]
        # title: walk up past the venue / city line
        title = ""
        for k in range(i - 1, max(i - 4, -1), -1):
            if lines[k].lower() in venue_names:
                continue
            title = lines[k]
            break
        title = re.sub(r"\s*\|\s*", ", ", title).strip()
        day = to_iso(m.group(1), m.group(2), m.group(3), today)
        pm = PRICE_LINE.match(price.replace(" ", "")) if price else None
        out.append(dict(title=title, date=day, show_time=fmt_time(m.group(4)),
                        price=money(pm.group(1)) if pm else "", free=False))
    return [c for c in out if c["title"] and c["date"] and c["date"] >= today]


def run():
    from playwright.sync_api import sync_playwright
    today = today_iso()
    out, ok = [], 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        for v in VENUES:
            cards, links, used = [], [], ""
            for url in v["urls"]:
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                    pg.wait_for_timeout(7000)
                    for _ in range(6):
                        pg.mouse.wheel(0, 5000)
                        pg.wait_for_timeout(600)
                except Exception as ex:
                    print(" ", v["name"], url, "failed:", str(ex).splitlines()[0])
                    continue
                # the shows may be on the page itself or in an embedded frame (the Shotgun widget)
                for fr in [pg] + [f for f in pg.frames if f != pg.main_frame]:
                    try:
                        text = fr.inner_text("body") if fr is not pg else pg.inner_text("body")
                        found = parse_text(text, today, v["names"])
                        if found:
                            cards = found
                            used = url
                            links = fr.eval_on_selector_all("a[href*='/events/']", "els => els.map(e => e.href)") if fr is not pg \
                                else pg.eval_on_selector_all("a[href*='/events/']", "els => els.map(e => e.href)")
                            break
                    except Exception:
                        continue
                if cards:
                    break
                allt = pg.inner_text("body")
                print(f"  DEBUG {v['name']} {url}: no shows read. Page title {pg.title()!r}; frames: {[f.url[:60] for f in pg.frames]}")
                print("   page text starts:", repr(allt[:500]))
            uniq = []
            for l in links:
                if l not in uniq:
                    uniq.append(l)
            for n, c in enumerate(cards):
                href = uniq[n] if len(uniq) == len(cards) else (v["urls"][-1] if "shotgun" in v["urls"][-1] else used)
                out.append(event(
                    id=f"shotgun-{slug(v['name'])}-{c['date']}-{slug(c['title'])}", title=c["title"], date=c["date"],
                    show_time=c["show_time"], venue=v["name"], url=href, ticket_url=href, kind="m",
                    address=v["address"], price_display=c["price"], free=c["free"]))
                print(" ", v["name"], c["date"], "|", c["title"][:45], "|", c["price"] or "no price", "|", c["show_time"])
            print(f"{v['name']}: {len(cards)} shows" + (f" (read from {used})" if used else ""))
            ok += 1 if cards else 0
        b.close()
    if not out or not ok:
        print("No shows came back, so shotgun.json was left alone.")
        sys.exit(1)
    save("shotgun.json", [v["name"] for v in VENUES], out)
    print(f"Saved {len(out)} shows")


if __name__ == "__main__":
    run()
