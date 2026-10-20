"""
Rally scraper for The Get Tight Lounge. Their calendar is a separate page
(calendar.gettightrva.com/shows) that we read directly. Writes gettight.json.
"""
import re
import sys
from rally_common import fmt_time, iso, slug, money, save, event, today_iso

LIST = "https://calendar.gettightrva.com/shows"
VENUE = "The Get Tight Lounge"
ADDRESS = "Richmond, VA"
DATE = re.compile(r"^([A-Z]+) (\d{1,2}), (\d{4})$")
AGE = re.compile(r"^(ALL AGES|\d{2}\+)$")
NOT_MUSIC = re.compile(r"watch party|karaoke|crabs|trivia|bingo", re.I)


def price_of(s):
    s = s.strip()
    if re.fullmatch(r"free", s, re.I):
        return "Free", True
    m = re.fullmatch(r"free to \$(\d+(?:\.\d{2})?)", s, re.I)
    if m:
        return f"Free to {money(m.group(1))}", False
    m = re.fullmatch(r"\$(\d+(?:\.\d{2})?) to \$(\d+(?:\.\d{2})?)", s, re.I)
    if m:
        return f"{money(m.group(1))}–{money(m.group(2))}", False
    m = re.fullmatch(r"\$(\d+(?:\.\d{2})?)", s)
    if m:
        return money(m.group(1)), False
    return "", False


def parse(body, links, today):
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    raw = []
    prev_end = 0
    for i, l in enumerate(lines):
        m = DATE.match(l)
        if not m or m.group(1).lower()[:3] not in ("jan feb mar apr may jun jul aug sep oct nov dec".split()):
            continue
        title = lines[prev_end] if prev_end < i else lines[i - 1]
        time_s = lines[i + 1] if i + 1 < len(lines) else ""
        age = lines[i + 2] if i + 2 < len(lines) and AGE.match(lines[i + 2]) else ""
        price_line = lines[i + 3] if age and i + 3 < len(lines) else (lines[i + 2] if i + 2 < len(lines) else "")
        price, free = price_of(price_line)
        raw.append(dict(title=title, day=iso(m.group(1), m.group(2), m.group(3)), time=fmt_time(time_s),
                        age=age.replace("ALL AGES", "All Ages"), price=price, free=free))
        j = i + 1
        while j < len(lines) and lines[j] != "BUY NOW":
            j += 1
        prev_end = j + 1
    use_links = len(links) == len(raw)
    out, seen = [], set()
    for n, r in enumerate(raw):
        if r["day"] < today:
            continue
        eid = f"gettight-{r['day']}-{slug(r['title'])}-{slug(r['time'])}"
        if eid in seen:
            continue
        seen.add(eid)
        out.append(event(
            id=eid, title=re.sub(r"\s+W/\s+", ", ", re.sub(r"\s+", " ", r["title"]).strip()),
            date=r["day"], show_time=r["time"], venue=VENUE, url=links[n] if use_links else LIST,
            kind="o" if NOT_MUSIC.search(r["title"]) else "m", age=r["age"], address=ADDRESS,
            price_display=r["price"], free=r["free"]))
    return out


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
            "a", "els => els.filter(e => /^buy now/i.test(e.innerText.trim())).map(e => e.href)")
        b.close()
    events = parse(body, links, today_iso())
    if len(events) < 3:
        print(f"Only {len(events)} shows came back, so gettight.json was left alone.")
        sys.exit(1)
    save("gettight.json", [VENUE], events)
    print(f"Saved {len(events)} shows")
    for e in events[:5]:
        print(" ", e["date"], e["show_time"], e["title"], "|", e["price_display"])


if __name__ == "__main__":
    main()
