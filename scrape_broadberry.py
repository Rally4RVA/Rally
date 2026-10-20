"""
Rally scraper for The Broadberry, Richmond Music Hall and Virginia Credit Union Live.
They all list their shows on the Broadberry homepage calendar. Writes broadberry.json.
Prices are not listed on this site, so shows link to tickets instead.
"""
import re
import sys
from rally_common import fmt_time, iso, slug, save, event, today_iso

URL = "https://thebroadberry.com/"
VENUES = ("The Broadberry", "Richmond Music Hall", "Virginia Credit Union Live")
MONTH_HEAD = re.compile(r"^([A-Z][a-z]+) (\d{4})$")
DAY = re.compile(r"^([A-Z]{3}) (\d{1,2})$")


def tidy(t):
    t = re.sub(r"\s+W/\s+", ", ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse(body, links, today):
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    year, out, n_more = None, [], 0
    i = 0
    while i < len(lines):
        m = MONTH_HEAD.match(lines[i])
        if m and m.group(1)[:3].lower() in ("jan feb mar apr may jun jul aug sep oct nov dec".split()):
            year = m.group(2)
            i += 1
            continue
        d = DAY.match(lines[i])
        if not d or not year:
            i += 1
            continue
        j = i + 1
        block = []
        while j < len(lines) and not DAY.match(lines[j]) and not MONTH_HEAD.match(lines[j]) \
                and lines[j] != "Previous" and not lines[j].startswith("Skip"):
            block.append(lines[j])
            j += 1
        i = j
        venue_i = next((k for k, l in enumerate(block) if l in VENUES), None)
        if venue_i is None or any("PRIVATE EVENT" in l for l in block):
            continue
        title = tidy(" ".join(block[:venue_i]))
        pre = block[:venue_i]
        doors = ""
        age = ""
        title_lines = []
        for l in pre:
            if l.lower().startswith("door"):
                doors = fmt_time(l)
            elif l.lower().startswith("ages"):
                am = re.search(r"(\d+)", l)
                age = (am.group(1) + "+") if am else ""
            else:
                title_lines.append(l)
        title = tidy(" ".join(title_lines))
        for l in block[:venue_i]:
            if l.lower().startswith("door") and not doors:
                doors = fmt_time(l)
        after = block[venue_i + 1:]
        sold = any("sold out" in l.lower() for l in after)
        day_iso = iso(d.group(1), d.group(2), year)
        if day_iso < today or not title:
            continue
        idx = len(out)
        url = links[idx] if idx < len(links) else ""
        out.append(event(
            id=f"bb-{day_iso}-{slug(title)}", title=title, date=day_iso, doors=doors, show_time="",
            venue=block[venue_i], url=url, age=age, price_display="Sold out" if sold else ""))
    # If the link list lost step with the show list, send everyone to the calendar page instead.
    if len(links) != len(out):
        for e in out:
            e["url"] = e["ticket_url"] = ""
    seen, unique = set(), []
    for e in out:                      # the page repeats some shows further down
        if e["id"] not in seen:
            seen.add(e["id"])
            e["url"] = e["ticket_url"] = e["url"] or "https://thebroadberry.com/events/"
            unique.append(e)
    return unique


def main():
    from playwright.sync_api import sync_playwright
    today = today_iso()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(6000)
        body = pg.inner_text("body")
        # "More Info" link of every real show, in page order (private events have none)
        links = pg.eval_on_selector_all("a", "els => els.filter(e => /^more info/i.test(e.innerText.trim())).map(e => e.href)")
        b.close()
    events = parse(body, links, today)
    if len(events) < 5:
        print(f"Only {len(events)} shows came back, so broadberry.json was left alone.")
        sys.exit(1)
    save("broadberry.json", sorted(set(e["venue"] for e in events)), events)
    print(f"Saved {len(events)} shows")
    for e in events[:8]:
        print(" ", e["date"], e["doors"], e["venue"], "|", e["title"])


if __name__ == "__main__":
    main()
