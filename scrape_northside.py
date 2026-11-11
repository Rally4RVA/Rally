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
TIME_LINE = re.compile(r"([A-Z][a-z]{2})[a-z]* (\d{1,2})(?:,? (\d{4}))?(?:,| at|\s·|\s-)?\s*(\d{1,2}(?::\d{2})?\s?[AaPp]\.?[Mm]\.?)(?:\s*[–-]\s*(\d{1,2}(?::\d{2})?\s?[AaPp]\.?[Mm]\.?))?")
HEADING = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),? ([A-Z][a-z]{2})[a-z]* (\d{1,2})(?:,? (\d{4}))?$")
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


def year_for(mon, dom, today, year=None):
    if year:
        return int(year)
    y = int(today[:4])
    # no year printed: this year, or next year if that month is already well behind us
    if mon < int(today[5:7]) - 1:
        y += 1
    return y


def parse(body, today):
    """The list is one card per show: a date heading ('Wed, Nov 11'), the band, '/', the venue, then 'Band Link' or 'Buy Tickets'.
    A time or price line inside the card is used if the site prints one."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in body.splitlines() if l.strip()]
    heads = [(i, HEADING.match(l)) for i, l in enumerate(lines) if HEADING.match(l)]
    out = []
    for n, (i, m) in enumerate(heads):
        mon = MONTHS.get(m.group(1).lower())
        if not mon:
            continue
        day = f"{year_for(mon, int(m.group(2)), today, m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        card = lines[i + 1:end]
        title = next((l for l in card if l != "/" and not SKIP.match(l) and not re.match(r"^buy tickets?$", l, re.I)
                      and not TIME_LINE.search(l)), "")
        text = " ".join(card)
        t = re.search(r"(\d{1,2}(?::\d{2})?\s?[AaPp]\.?[Mm]\.?)", text)
        price, free = price_in(text)
        ticketed = any(re.match(r"^buy tickets?$", l, re.I) for l in card)
        if not price:
            price, free = ("", False) if ticketed else ("Free", True)
        if day < today or not title:
            continue
        out.append(dict(title=clean_title(title), date=day, show_time=fmt_time(t.group(1)) if t else "",
                        patio=bool(re.search(r"patio", text, re.I)), price=price, free=free, card=n))
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
    total = sum(1 for l in body.splitlines() if HEADING.match(re.sub(r"\s+", " ", l).strip()))
    if total == 0:                                  # show what the page looked like, so the log says why
        print("  --- page text (first 60 lines) ---")
        for l in [x.strip() for x in body.splitlines() if x.strip()][:60]:
            print("  |", l[:120])
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
