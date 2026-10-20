"""
Rally scraper for Bandito's Burrito Lounge.
Their calendar page is an Opendate list, which we read directly, then each show's ticket
page for the price. Writes bandito.json.
"""
import re
import sys
from rally_common import fmt_time, iso, slug, save, event, today_iso

PAGE = "https://www.banditosburritolounge.com/event-calendar"
LIST = "https://app.opendate.io/v/bandito-s-burrito-lounge-3292?layout=iframe"
VENUE = "Bandito's Burrito Lounge"
ADDRESS = "2905 Patterson Ave, Richmond, VA"
DATE = re.compile(r"^([A-Z][a-z]+) (\d{1,2}), (\d{4})$")
HOURS = re.compile(r"^Doors:\s*(\S+ ?[AP]M)\s*-\s*Show:\s*(\S+ ?[AP]M)", re.I)


def tidy(t):
    t = re.sub(r"\s+w/\s+", ", ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def parse(body, links, today):
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    raw = []
    for i, l in enumerate(lines):
        m = DATE.match(l)
        if not m or i == 0:
            continue
        h = HOURS.match(lines[i + 1]) if i + 1 < len(lines) else None
        raw.append((lines[i - 1], iso(m.group(1), m.group(2), m.group(3)),
                    fmt_time(h.group(1)) if h else "", fmt_time(h.group(2)) if h else ""))
    use_links = len(links) == len(raw)
    out, seen = [], set()
    for n, (title, day, doors, show) in enumerate(raw):
        if day < today:
            continue
        eid = f"bandito-{day}-{slug(title)}"
        if eid in seen:
            continue
        seen.add(eid)
        out.append(event(id=eid, title=tidy(title), date=day, doors=doors, show_time=show, venue=VENUE,
                         url=links[n] if use_links else PAGE, address=ADDRESS))
    return out


def add_prices(pg, events):
    """Each Opendate show page has the same checkout box as The Camel's, with the ticket price in it.
    Etix shows can't be read that way, so they stay on 'See tickets'."""
    from scrape_camel import parse_tiers, price_display, opendate_text, free_label, AGE_RE
    for e in events:
        if "opendate.io/e/" not in e["url"]:
            continue
        try:
            pg.goto(e["url"], wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(1500)
            _, text = opendate_text(pg, wait_s=12)
            tiers = parse_tiers(text)
            label = price_display(tiers) if tiers else free_label(text)
            if label:
                e["price_display"] = label
                e["free"] = label.startswith("Free")
                e["tiers"] = tiers
            age = next((l.strip() for l in text.splitlines() if AGE_RE.match(l.strip())), "")
            if age:
                e["age"] = age
        except Exception as ex:
            print("  price lookup failed for", e["title"], "-", str(ex).splitlines()[0])


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(LIST, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(8000)
        for _ in range(3):
            pg.mouse.wheel(0, 4000)
            pg.wait_for_timeout(700)
        body = pg.inner_text("body")
        links = pg.eval_on_selector_all(
            "a[href*='/e/'], a[href*='etix.com']", "els => els.map(e => e.href)")
        events = parse(body, links, today_iso())
        if len(events) < 3:
            print(f"Only {len(events)} shows came back, so bandito.json was left alone.")
            sys.exit(1)
        add_prices(pg, events)
        b.close()
    save("bandito.json", [VENUE], events)
    print(f"Saved {len(events)} shows")
    for e in events[:5]:
        print(" ", e["date"], e["show_time"], e["title"], "|", e["price_display"] or "see tickets")


if __name__ == "__main__":
    main()
