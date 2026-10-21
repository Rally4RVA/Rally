"""
Rally scraper for The Canal Club (thecanalclub.com/events). The list gives date, bands, age and times;
each TICKETS button goes to a Tixr page that shows the price ("Tickets: $22 / $25"). Writes canalclub.json.
"""
import re
import sys
from datetime import date
from rally_common import fmt_time, slug, money, save, event, today_iso, MONTHS

LIST = "https://thecanalclub.com/events/"
VENUE = "The Canal Club"
ADDRESS = "Richmond, VA"
DATE_LINE = re.compile(r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),? ([A-Za-z]+) (\d{1,2})(?:,? (\d{4}))?$")
TIMES = re.compile(r"Doors:?\s*(\d{1,2}(?::\d{2})?\s*[AP]M)(?:\s*\|\s*Show:?\s*(\d{1,2}(?::\d{2})?\s*[AP]M))?", re.I)
AGE = re.compile(r"^(?:All Ages|Ages? \d{2}\+|\d{2}\+)$", re.I)


def to_iso(mon_name, day, year, today):
    mon = MONTHS.get(mon_name[:3].lower())
    if not mon:
        return ""
    try:
        if year:
            return date(int(year), mon, int(day)).isoformat()
        d = date(int(today[:4]), mon, int(day))
        if d.isoformat() < today:      # the page has no year, so a past month/day means next year
            d = date(d.year + 1, mon, int(day))
        return d.isoformat()
    except ValueError:
        return ""


def parse(body, today):
    lines = [re.sub(r"\s+", " ", l).strip() for l in body.splitlines() if l.strip()]
    idx = [i for i, l in enumerate(lines) if DATE_LINE.match(l)]
    out = []
    for n, i in enumerate(idx):
        m = DATE_LINE.match(lines[i])
        day = to_iso(m.group(1), m.group(2), m.group(3), today)
        block = lines[i + 1: idx[n + 1] if n + 1 < len(idx) else len(lines)]
        title, support, age, doors, show = "", "", "", "", ""
        for l in block:
            tm = TIMES.search(l)
            if tm:
                doors, show = fmt_time(tm.group(1)), fmt_time(tm.group(2) or "")
                break
            if AGE.match(l):
                age = re.sub(r"^Ages? ", "", l, flags=re.I)
                age = "All Ages" if age.lower() == "all ages" else age
            elif l.lower().startswith("with "):
                support = l[5:].strip()
            elif not title:
                title = l
        if not (day and title) or day < today:
            continue
        full = f"{title}, {support}" if support else title
        out.append(dict(title=full, date=day, doors=doors, show_time=show, age=age, card=n))
    return out


def tixr_price(text):
    """'Tickets: $22 / $25' -> '$22–$25'. 'Sold out' pages come back as Sold out."""
    if re.search(r"sold out", text, re.I) and not re.search(r"\$\s?\d", text):
        return "Sold out", False
    m = re.search(r"Tickets?:?\s*\$\s?(\d+(?:\.\d{2})?)(?:\s*(?:/|-|–|to)\s*\$\s?(\d+(?:\.\d{2})?))?", text, re.I)
    if m:
        lo, hi = m.group(1), m.group(2)
        return (money(lo) if not hi or float(lo) == float(hi) else f"{money(lo)}–{money(hi)}"), False
    if re.search(r"\bfree\b", text[:2000], re.I) and not re.search(r"\$\s?\d", text):
        return "Free", True
    return "", False


def run():
    from playwright.sync_api import sync_playwright
    today = today_iso()
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(LIST, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        for _ in range(5):
            pg.mouse.wheel(0, 6000)
            pg.wait_for_timeout(600)
        body = pg.inner_text("body")
        links = pg.eval_on_selector_all(
            "a[href*='tixr.com']", "els => els.filter(e => /ticket/i.test(e.innerText)).map(e => e.href)")
        total = sum(1 for l in body.splitlines() if DATE_LINE.match(re.sub(r"\s+", " ", l).strip()))
        if len(links) != total:
            print(f"  note: {total} dates but {len(links)} ticket links, so shows link to the events page")
            links = []
        for s in parse(body, today):
            href = links[s["card"]] if links else LIST
            price, free = "", False
            if href != LIST:
                try:
                    pg.goto(href, wait_until="domcontentloaded", timeout=45000)
                    pg.wait_for_timeout(2500)
                    price, free = tixr_price(pg.inner_text("body"))
                except Exception as ex:
                    print("  could not read", s["title"], "-", str(ex).splitlines()[0])
            out.append(event(
                id=f"canalclub-{s['date']}-{slug(s['title'])}", title=s["title"], date=s["date"], doors=s["doors"],
                show_time=s["show_time"], venue=VENUE, url=href, ticket_url=href, kind="m", age=s["age"],
                address=ADDRESS, price_display=price, free=free))
            print(" ", s["date"], "|", s["title"][:50], "|", price or "no price")
        b.close()
    if len(out) < 3:
        print(f"Only {len(out)} shows came back, so canalclub.json was left alone.")
        sys.exit(1)
    save("canalclub.json", [VENUE], out)
    print(f"{VENUE}: saved {len(out)} shows")


if __name__ == "__main__":
    run()
