"""
Rally scraper for Northside Grille (thenorthsidegrille.com/band-calendar), a Wix event list with a "Load More" button.
Shows with no cover listed are shown as Free; shows that list a price ("$5 in advance, $10 day of show") keep it.
Writes northside.json.
"""
import re
import sys
from rally_common import fmt_time, slug, money, save, event, today_iso, MONTHS

LIST = "https://www.thenorthsidegrille.com/band-calendar"
VENUE = "Northside Grille"
ADDRESS = "1217 Bellevue Ave, Richmond, VA"
TIME_LINE = re.compile(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4}),? (\d{1,2}(?::\d{2})?\s?[AP]M)(?:\s*[–-]\s*(\d{1,2}(?::\d{2})?\s?[AP]M))?")
HEADING = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),? [A-Z][a-z]{2} \d{1,2}$")
SKIP = re.compile(r"^(?:Northside Grille(?: Patio)?|Patio Show|Band Link|Tickets?|Load More|Share|Facebook|Twitter|Link)$", re.I)


def clean_title(t):
    t = re.sub(r"\s*/\s*Northside Grille(?: Patio)?\s*$", "", t.strip(), flags=re.I)
    t = re.sub(r"\s+(?:with|w/)\s+", ", ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def price_in(text):
    m = re.search(r"\$\s?(\d+(?:\.\d{2})?)\s*(?:in advance|adv\w*)[^$]{0,25}\$\s?(\d+(?:\.\d{2})?)", text, re.I)
    if m:
        return f"{money(m.group(1))} adv · {money(m.group(2))} door", False
    m = re.search(r"\$\s?(\d+(?:\.\d{2})?)", text)
    if m:
        return money(m.group(1)), False
    return "", False


def parse(body, today):
    lines = [re.sub(r"\s+", " ", l).strip() for l in body.splitlines() if l.strip()]
    hits = [(i, TIME_LINE.search(l)) for i, l in enumerate(lines) if TIME_LINE.search(l)]
    out = []
    for n, (i, m) in enumerate(hits):
        day = f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
        # the title sits right after the date heading, a few lines above the time line
        title = ""
        for k in range(i - 1, max(i - 7, -1), -1):
            if HEADING.match(lines[k]):
                if k + 1 < i:
                    title = lines[k + 1]
                break
        if not title or SKIP.match(title):
            title = next((lines[k] for k in range(i - 1, max(i - 5, -1), -1)
                          if not HEADING.match(lines[k]) and not SKIP.match(lines[k]) and not TIME_LINE.search(lines[k])), "")
        end = hits[n + 1][0] - 1 if n + 1 < len(hits) else len(lines)
        after = " ".join(lines[i + 1:max(i + 1, end)][:8])
        price, free = price_in(after)
        if not price:
            price, free = "Free", True
        if day < today or not title:
            continue
        out.append(dict(title=clean_title(title), date=day, show_time=fmt_time(m.group(4)),
                        patio=bool(re.search(r"patio", " ".join(lines[max(i - 3, 0):i + 3]), re.I)),
                        price=price, free=free, card=n))
    return out


def run():
    from playwright.sync_api import sync_playwright
    today = today_iso()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(LIST, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(6000)
        for _ in range(12):                       # keep pressing "Load More" until it goes away
            btn = pg.locator("text=Load More").first
            try:
                if not btn.is_visible(timeout=1500):
                    break
                btn.click()
                pg.wait_for_timeout(1500)
            except Exception:
                break
        body = pg.inner_text("body")
        links = pg.eval_on_selector_all(
            "a[href*='/event-details/']", "els => els.map(e => e.href)")
        b.close()
    uniq = []
    for l in links:
        if l not in uniq:
            uniq.append(l)
    total = sum(1 for l in body.splitlines() if TIME_LINE.search(l))
    if len(uniq) != total:
        print(f"  note: {total} shows but {len(uniq)} event links, so shows link to the calendar page")
        uniq = []
    out = []
    for s in parse(body, today):
        href = uniq[s["card"]] if uniq else LIST
        out.append(event(
            id=f"northside-{s['date']}-{slug(s['title'])}", title=s["title"], date=s["date"], show_time=s["show_time"],
            venue=VENUE, url=href, ticket_url=href, kind="m", address=ADDRESS, price_display=s["price"], free=s["free"]))
        print(" ", s["date"], "|", s["title"][:50], "|", s["price"], "|", s["show_time"])
    if len(out) < 3:
        print(f"Only {len(out)} shows came back, so northside.json was left alone.")
        sys.exit(1)
    save("northside.json", [VENUE], out)
    print(f"{VENUE}: saved {len(out)} shows")


if __name__ == "__main__":
    run()
