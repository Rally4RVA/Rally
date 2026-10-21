"""
Rally scraper for Révéler (revelerexperiences.com/calendar), a jazz / soul / roots venue on W Cary St.
The calendar is a plain list. Each show's own page has the price ("Admission: $25") and the ticket link
(buytickets.at). Writes reveler.json.
"""
import re
import sys
from rally_common import fmt_time, iso, slug, money, save, event, today_iso

LIST = "https://www.revelerexperiences.com/calendar"
VENUE = "Révéler"
ADDRESS = "3108 W Cary St, Richmond, VA"
DATE_RE = re.compile(r"(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER) (\d{1,2}),? (\d{4})", re.I)
TIME_RE = re.compile(r"\d{1,2}(?::\d{2})?\s?[AP]M", re.I)
DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


def parse_card(text):
    """One calendar entry's text -> (title, date, [times], label). The title can appear twice, so repeats are dropped."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()]
    flat = " ".join(lines)
    m = DATE_RE.search(flat)
    if not m:
        return None
    day = iso(m.group(1), m.group(2), m.group(3))
    # title = everything before the weekday / date, with repeated phrases removed
    head = []
    for l in lines:
        if l.upper() in DAYS or DATE_RE.search(l):
            break
        if l not in head:
            head.append(l)
    title = " ".join(head)
    if not head:   # everything ran together on one line
        before = flat[:m.start()].strip()
        before = re.sub(r"(MON|TUE|WED|THU|FRI|SAT|SUN)$", "", before).strip()
        title = re.sub(r"(.{8,}?)\1+", r"\1", before)   # a phrase printed twice in a row
    after = flat[m.end():]
    times = [fmt_time(t) for t in TIME_RE.findall(after)[:2]]
    label = "sold out" if re.search(r"sold out", flat, re.I) else ""
    return title.strip(), day, [t for t in times if t], label


def detail(text):
    """Price, age and ticket hints from a show's own page."""
    price, free = "", False
    m = re.search(r"Admission:?\s*\$\s?(\d+(?:\.\d{2})?)(?:\s*(?:-|–|to)\s*\$\s?(\d+(?:\.\d{2})?))?", text, re.I)
    if m:
        price = money(m.group(1)) if not m.group(2) else f"{money(m.group(1))}–{money(m.group(2))}"
    elif re.search(r"Admission:?\s*free|no cover|free admission|\bfree show\b", text, re.I):
        price, free = "Free", True
    else:
        m = re.search(r"\$\s?(\d+(?:\.\d{2})?)", text)
        if m:
            price = money(m.group(1))
    am = re.search(r"(\d{2})\+", text)
    return price, free, (am.group(1) + "+") if am else ""


def run():
    from playwright.sync_api import sync_playwright
    today = today_iso()
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(LIST, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        for _ in range(4):
            pg.mouse.wheel(0, 5000)
            pg.wait_for_timeout(600)
        cards = pg.eval_on_selector_all(
            "a[href*='/event/']", "els => els.map(e => [e.innerText, e.href])")
        seen = set()
        for text, href in cards:
            if href in seen:
                continue
            seen.add(href)
            parsed = parse_card(text)
            if not parsed:
                continue
            title, day, times, label = parsed
            if day < today or not title:
                continue
            price, free, age, ticket = "", False, "", href
            try:
                pg.goto(href, wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_timeout(1200)
                body = pg.inner_text("body")
                price, free, age = detail(body)
                hrefs = pg.eval_on_selector_all("a[href*='buytickets.at']", "els => els.map(a => a.href)")
                if hrefs:
                    ticket = hrefs[0]
            except Exception as ex:
                print("  could not read", title, "-", str(ex).splitlines()[0])
            if label == "sold out":
                price, free = "Sold out", False
            for t in (times or [""]):
                out.append(event(
                    id=f"reveler-{day}-{slug(title)}-{slug(t)}", title=title.title() if title.isupper() else title,
                    date=day, doors="", show_time=t, venue=VENUE, url=href, ticket_url=ticket, kind="m",
                    age=age, address=ADDRESS, price_display=price, free=free))
            print(" ", day, "|", title, "|", price or "no price", "|", ", ".join(times))
        b.close()
    if len(out) < 3:
        print(f"Only {len(out)} shows came back, so reveler.json was left alone.")
        sys.exit(1)
    save("reveler.json", [VENUE], out)
    print(f"{VENUE}: saved {len(out)} shows")


if __name__ == "__main__":
    run()
