"""
Rally scraper for Brambly Park (bramblypark.com/eventscalendar). The calendar is cards (date badge, title, time range)
that load with JavaScript, with a "Next" button for the following month. Writes brambly.json.
"""
import re
import sys
from datetime import date
from rally_common import fmt_time, slug, save, event, today_iso, MONTHS

LIST = "https://www.bramblypark.com/eventscalendar"
VENUE = "Brambly Park"
ADDRESS = "1708 Belleville St, Richmond, VA"
DEFAULT_PRICE = "Free"   # the cards list no price, and Brambly Park shows are always free
MONTH_HEAD = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})$")
MON = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$")
DOW = re.compile(r"^(MON|TUE|WED|THU|FRI|SAT|SUN)$")
RANGE = re.compile(r"^(\d{1,2}(?::\d{2})?\s?[AP]M)(?:\s*[-–]\s*(\d{1,2}(?::\d{2})?\s?[AP]M))?$", re.I)
NOT_MUSIC = re.compile(r"wine down|trivia|bingo|yoga|market|class\b|workshop|paint|tasting|dinner|brunch|run club|bark", re.I)


def parse(body, today):
    lines = [re.sub(r"\s+", " ", l).strip() for l in body.splitlines() if l.strip()]
    year, out = None, []
    i = 0
    while i < len(lines):
        m = MONTH_HEAD.match(lines[i])
        if m:
            year = int(m.group(2))
            i += 1
            continue
        if year and i + 3 < len(lines) and MON.match(lines[i]) and lines[i + 1].isdigit() and DOW.match(lines[i + 2]):
            mon, dnum = MONTHS[lines[i].lower()], int(lines[i + 1])
            title = lines[i + 3]
            tm = RANGE.match(lines[i + 4]) if i + 4 < len(lines) else None
            try:
                day = date(year, mon, dnum).isoformat()
            except ValueError:
                i += 1
                continue
            if day >= today and title and not MON.match(title):
                out.append(dict(title=title, date=day, show_time=fmt_time(tm.group(1)) if tm else "",
                                music=not NOT_MUSIC.search(title)))
            i += 5 if tm else 4
            continue
        i += 1
    return out


def run():
    from playwright.sync_api import sync_playwright
    today = today_iso()
    found, seen = [], set()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(LIST, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(7000)
        for month in range(4):                    # this month plus the next three
            for _ in range(4):
                pg.mouse.wheel(0, 4000)
                pg.wait_for_timeout(500)
            for s in parse(pg.inner_text("body"), today):
                key = (s["date"], s["title"], s["show_time"])
                if key not in seen:
                    seen.add(key)
                    found.append(s)
            try:
                nxt = pg.locator("button:has-text('Next'), a:has-text('Next')").first
                if not nxt.is_visible(timeout=1500):
                    break
                nxt.click()
                pg.wait_for_timeout(2500)
            except Exception:
                break
        b.close()
    out = []
    for s in found:
        out.append(event(
            id=f"brambly-{s['date']}-{slug(s['title'])}", title=s["title"], date=s["date"], show_time=s["show_time"],
            venue=VENUE, url=LIST, ticket_url=LIST, kind="m" if s["music"] else "o", address=ADDRESS,
            price_display=DEFAULT_PRICE if s["music"] else "",
            free=bool(s["music"]) and DEFAULT_PRICE.lower().startswith("free")))
        print(" ", s["date"], "|", s["title"][:50], "|", s["show_time"], "|", "music" if s["music"] else "not a gig")
    if len(out) < 3:
        print(f"Only {len(out)} shows came back, so brambly.json was left alone.")
        sys.exit(1)
    save("brambly.json", [VENUE], out)
    print(f"{VENUE}: saved {len(out)} shows")


if __name__ == "__main__":
    run()
