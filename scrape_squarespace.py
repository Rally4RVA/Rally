"""
Rally scraper for venues whose calendar is a Squarespace event list:
Gallery5 (gallery5arts.org/calendar), Hardywood (hardywood.com/richmond-events) and
Main Line Brewery (mainlinerva.com/eventsatmainline). Writes gallery5.json, hardywood.json, mainline.json.
"""
import re
import sys
from rally_common import fmt_time, iso, slug, money, save, event, today_iso

LONG_DATE = re.compile(r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), ([A-Z][a-z]+) (\d{1,2}), (\d{4})$")
SHORT_DATE = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), ([A-Z][a-z]{2}) (\d{1,2}), (\d{4})")
TIME = re.compile(r"\d{1,2}(?::\d{2})?\s?[AP]M", re.I)

# Shows that are not live music get a "not a gig" tag and are hidden by "Music only".
G5_NOT_MUSIC = re.compile(r"town hall|happy hour|reception|drag|exhibit|workshop|class\b|open house|market|bazaar|screening|film|poetry|comedy|trivia|bingo|yoga", re.I)
ML_NOT_MUSIC = re.compile(r"training|5k|meetup|market|networking|block party|oyster|pug-o-ween|dead people|history month|celebration|yoga|trivia|bingo|class\b|fundrais", re.I)
HW_MUSIC = re.compile(r"live music|bluegrass|throwdown|jam\b|symphony|mambo|concert|band\b", re.I)

VENUES = {
    "gallery5": {
        "name": "Gallery5", "url": "https://gallery5arts.org/calendar",
        "address": "200 W Marshall St, Richmond, VA", "file": "gallery5.json",
    },
    "mainline": {
        "name": "Main Line Brewery", "url": "https://www.mainlinerva.com/eventsatmainline",
        "address": "1603 Ownby Ln, Richmond, VA", "file": "mainline.json",
    },
    "hardywood": {
        "name": "Hardywood", "url": "https://www.hardywood.com/richmond-events",
        "address": "2410 Ownby Ln, Richmond, VA", "file": "hardywood.json",
    },
}


def find_date(line):
    m = LONG_DATE.match(line)
    if m:
        return iso(m.group(1), m.group(2), m.group(3))
    m = SHORT_DATE.match(line)
    if m:
        return iso(m.group(1), m.group(2), m.group(3))
    return None


def gallery_price(text):
    """Prices are written into the description, e.g. '$8 adv / $12 dos.', '$15 cover.', '$15.', 'no charge'."""
    m = re.search(r"\$(\d+(?:\.\d{2})?)\s*adv\w*\s*/\s*\$(\d+(?:\.\d{2})?)\s*(?:dos|door|day)", text, re.I)
    if m:
        return f"{money(m.group(1))} adv · {money(m.group(2))} door", False
    m = re.search(r"(?m)^\s*\$(\d+(?:\.\d{2})?)\s*(?:cover|admission|tickets?)?\.?\s*$", text, re.I) \
        or re.search(r"\$(\d+(?:\.\d{2})?)\s*(?:cover|admission)", text, re.I)
    if m:
        return money(m.group(1)), False
    if re.search(r"\bfree\b|no charge", text, re.I):
        return "Free", True
    return "", False


FREE_RE = re.compile(r"free show|free event|free admission|free entry|free music|free concert|no cover|free to attend|\bfree!", re.I)
ADV_RE = re.compile(r"(?:adv(?:ance)?\b)[^$\n]{0,15}\$\s?(\d+(?:\.\d{2})?)|\$\s?(\d+(?:\.\d{2})?)\s*(?:adv(?:ance)?\b)", re.I)
DOOR_RE = re.compile(r"(?:door|day of show|day-of|\bdos\b)[^$\n]{0,15}\$\s?(\d+(?:\.\d{2})?)|\$\s?(\d+(?:\.\d{2})?)\s*(?:at the door|at door|door|dos\b|day of)", re.I)


def detail_price(text):
    """Price from a show's own page: 'FREE SHOW!', '$15 advance / $20 at door', 'GA Advance $25 ... Day of Show $30'."""
    a = ADV_RE.search(text)
    d = DOOR_RE.search(text)
    if a or d:
        av = next((g for g in a.groups() if g), None) if a else None
        dv = next((g for g in d.groups() if g), None) if d else None
        if av and dv:
            return f"{money(av)} adv · {money(dv)} door", False
        if av:
            return f"{money(av)} adv", False
        return f"{money(dv)} door", False
    if FREE_RE.search(text):
        return "Free", True
    m = re.search(r"(?:cover|tickets?|admission)\D{0,12}\$\s?(\d+(?:\.\d{2})?)|\$\s?(\d+(?:\.\d{2})?)\s*(?:cover|admission)", text, re.I)
    if m:
        return money(next(g for g in m.groups() if g)), False
    return "", False


def parse(body, key, links, today):
    cfg = VENUES[key]
    lines = [l.strip() for l in body.splitlines()]
    idx = [i for i, l in enumerate(lines) if find_date(l)]
    out = []
    for n, i in enumerate(idx):
        day = find_date(lines[i])
        j = i - 1
        while j >= 0 and not lines[j]:
            j -= 1
        title = re.sub(r"\s+", " ", lines[j]).strip()
        nxt = idx[n + 1] if n + 1 < len(idx) else len(lines)
        desc = [l for l in lines[i + 1:nxt - 1] if l]
        # the next show's title sits just before its date line, so stop one non-empty line short
        times = TIME.findall(re.sub(r"(\d{4})(?=\d{1,2}:\d{2})", r"\1 ", lines[i])) if SHORT_DATE.match(lines[i]) and not LONG_DATE.match(lines[i]) else []
        times = times or (TIME.findall(desc[0]) if desc else [])
        start = fmt_time(times[0]) if times else ""
        text = "\n".join(desc)
        doors, show = "", start
        dm = re.search(r"Doors?\s*(\d{1,2}(?::\d{2})?)\s*(?:\|)\s*Show\s*(\d{1,2}(?::\d{2})?)", text, re.I)
        if dm:
            ap = "PM"
            doors, show = fmt_time(dm.group(1) + ap.lower()), fmt_time(dm.group(2) + ap.lower())
        age = "18+" if re.search(r"18\+", text) else ("21+" if re.search(r"21\+", text) else "")
        if key == "gallery5":
            price, free = gallery_price(text)
            music = not G5_NOT_MUSIC.search(title)
            if re.search(r"jazz night", title, re.I):
                music = True
        elif key == "mainline":
            price, free = gallery_price(text)
            music = not ML_NOT_MUSIC.search(title)
        else:
            price, free = "", False
            music = bool(HW_MUSIC.search(title))
        shown = re.sub(r"^LIVE MUSIC:\s*", "", title)
        shown = re.sub(r"\s+w/\s+", ", ", shown, flags=re.I)
        if day < today:
            continue
        url = links.get(title, cfg["url"])
        out.append(event(
            id=f"{key}-{day}-{slug(title)}", title=shown, date=day, doors=doors, show_time=show,
            venue=cfg["name"], url=url, kind="m" if music else "o", age=age,
            address=cfg["address"], price_display=price, free=free))
    return out


def eventbrite_price(pg, url):
    """Open an Eventbrite event page and read the ticket price: JSON-LD offers first, then the visible text."""
    import json
    pg.goto(url, wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(2500)
    lows, highs = [], []
    for raw in pg.eval_on_selector_all("script[type='application/ld+json']", "els => els.map(e => e.textContent)"):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for item in (data if isinstance(data, list) else [data]):
            offers = item.get("offers") if isinstance(item, dict) else None
            for o in (offers if isinstance(offers, list) else [offers] if offers else []):
                if not isinstance(o, dict):
                    continue
                for k, bucket in (("lowPrice", lows), ("price", lows), ("highPrice", highs)):
                    try:
                        bucket.append(float(o[k]))
                    except Exception:
                        pass
    body = pg.inner_text("body")
    if lows:
        lo, hi = min(lows), max(highs or lows)
        if hi == 0:
            return "Free", True
        return (money(lo) if lo == hi else f"{money(lo)}–{money(hi)}"), False
    m = re.search(r"\$\s?(\d+(?:\.\d{2})?)", body)
    if m:
        return money(m.group(1)), False
    if re.search(r"(?m)^\s*Free\s*$", body):
        return "Free", True
    return "", False


def run(key):
    from playwright.sync_api import sync_playwright
    cfg = VENUES[key]
    today = today_iso()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(cfg["url"], wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        for _ in range(4):
            pg.mouse.wheel(0, 4000)
            pg.wait_for_timeout(700)
        body = pg.inner_text("body")
        pairs = pg.eval_on_selector_all(
            "a.eventlist-title-link, h1 a[href*='/calendar/'], h1 a[href*='events']",
            "els => els.map(e => [e.innerText.trim(), e.href])")
        b.close()
    links = {t: h for t, h in pairs}
    events = parse(body, key, links, today)
    if key == "mainline" and events:
        # The price ("FREE SHOW!", "$15 advance") is written on each show's own page.
        with sync_playwright() as p2:
            b2 = p2.chromium.launch(headless=True)
            pg2 = b2.new_page()
            for e in events:
                if not e["url"] or e["url"] == cfg["url"] or e["price_display"]:
                    continue
                try:
                    pg2.goto(e["url"], wait_until="domcontentloaded", timeout=45000)
                    pg2.wait_for_timeout(1200)
                    e["price_display"], e["free"] = detail_price(pg2.inner_text("body"))
                except Exception as ex:
                    print("  could not read", e["title"], "-", str(ex).splitlines()[0])
            b2.close()
    if key in ("gallery5", "hardywood") and events:
        # No price on the calendar: open the show's page, and if it links to Eventbrite, read the price there.
        with sync_playwright() as p3:
            b3 = p3.chromium.launch(headless=True)
            pg3 = b3.new_page()
            for e in events:
                if e["price_display"] or not e["url"] or e["url"] == cfg["url"]:
                    continue
                try:
                    pg3.goto(e["url"], wait_until="domcontentloaded", timeout=45000)
                    pg3.wait_for_timeout(1200)
                    text = pg3.inner_text("body")
                    price, free = detail_price(text)
                    hrefs = pg3.eval_on_selector_all(
                        "a[href*='eventbrite.com/e/'], a[href*='eventbrite.com/tickets']", "els => els.map(a => a.href)")
                    if hrefs:
                        e["ticket_url"] = hrefs[0]
                        if not price:
                            price, free = eventbrite_price(pg3, hrefs[0])
                    e["price_display"], e["free"] = price, free
                    print("  price", e["title"], "->", price or "none", "(eventbrite)" if hrefs else "")
                except Exception as ex:
                    print("  could not read", e["title"], "-", str(ex).splitlines()[0])
            b3.close()
    if not events:
        print(f"No shows came back for {cfg['name']}, so {cfg['file']} was left alone.")
        sys.exit(1)
    save(cfg["file"], [cfg["name"]], events)
    print(f"{cfg['name']}: saved {len(events)} shows")
    for e in events[:6]:
        print(" ", e["date"], e["show_time"], e["title"], "|", e["price_display"] or "-", "|", e["kind"])


if __name__ == "__main__":
    run(sys.argv[1])
