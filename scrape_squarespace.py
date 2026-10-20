"""
Rally scraper for venues whose calendar is a Squarespace event list:
Gallery5 (gallery5arts.org/calendar) and Hardywood (hardywood.com/richmond-events).
Writes gallery5.json and hardywood.json.
"""
import re
import sys
from rally_common import fmt_time, iso, slug, money, save, event, today_iso

LONG_DATE = re.compile(r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), ([A-Z][a-z]+) (\d{1,2}), (\d{4})$")
SHORT_DATE = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), ([A-Z][a-z]{2}) (\d{1,2}), (\d{4})")
TIME = re.compile(r"\d{1,2}(?::\d{2})?\s?[AP]M", re.I)

# Shows that are not live music get a "not a gig" tag and are hidden by "Music only".
G5_NOT_MUSIC = re.compile(r"town hall|happy hour|reception|drag|exhibit|workshop|class\b|open house|market|bazaar|screening|film|poetry|comedy|trivia|bingo|yoga", re.I)
HW_MUSIC = re.compile(r"live music|bluegrass|throwdown|jam\b|symphony|mambo|concert|band\b", re.I)

VENUES = {
    "gallery5": {
        "name": "Gallery5", "url": "https://gallery5arts.org/calendar",
        "address": "200 W Marshall St, Richmond, VA", "file": "gallery5.json",
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
    if not events:
        print(f"No shows came back for {cfg['name']}, so {cfg['file']} was left alone.")
        sys.exit(1)
    save(cfg["file"], [cfg["name"]], events)
    print(f"{cfg['name']}: saved {len(events)} shows")
    for e in events[:6]:
        print(" ", e["date"], e["show_time"], e["title"], "|", e["price_display"] or "-", "|", e["kind"])


if __name__ == "__main__":
    run(sys.argv[1])
