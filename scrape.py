"""Fetch Monopoly GO reward links from monopolygo.wiki and save the newest ones to links.json.
Only the official mply.io links + reward amount are kept (no text is copied)."""
import json, re, sys, datetime, urllib.request
from html.parser import HTMLParser

SOURCE = "https://monopolygo.wiki/latest-reward-links"
OUT = "links.json"
MAX_LINKS = 3
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.geturl(), r.read().decode("utf-8", "ignore")

class Links(HTMLParser):
    """Collect every <a> with its text + the text of the surrounding row/item."""
    BLOCK = {"tr", "li", "div", "p", "article", "section"}
    def __init__(s):
        super().__init__(); s.items = []; s.stack = []; s.cur = None
    def handle_starttag(s, tag, a):
        a = dict(a)
        if tag in s.BLOCK: s.stack.append([tag, ""])
        if tag == "a" and a.get("href"): s.cur = {"href": a["href"], "text": "", "block": len(s.stack) - 1}
    def handle_endtag(s, tag):
        if tag == "a" and s.cur:
            s.items.append(s.cur); s.cur["ctx_ref"] = s.stack[s.cur["block"]] if s.cur["block"] >= 0 else ["", ""]; s.cur = None
        if tag in s.BLOCK and s.stack:
            s.stack.pop()
    def handle_data(s, d):
        for b in s.stack: b[1] += " " + d
        if s.cur: s.cur["text"] += d

def resolve(href):
    """Return the final mply.io URL (follows the site's own short links if needed)."""
    if "mply.io" in href:
        return href.split("?")[0]
    if re.search(r"mplygo\.wiki|monopolygo\.wiki/(go|l|r)/", href):
        try:
            final, _ = get(href)
            if "mply.io" in final: return final.split("?")[0]
        except Exception: pass
    return None

def reward(text):
    t = " ".join(text.split())
    m = re.search(r"(\d{2,4})\s*(?:free\s*)?(?:dice|rolls?)", t, re.I)
    if m: return f"{m.group(1)} Free Dice Rolls"
    for w in ("sticker", "token", "cash", "shield"):
        if w in t.lower(): return "Free " + w.capitalize() + " Reward"
    return "Free Dice Rolls"

def main():
    try:
        old = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        old = {"links": []}
    seen = {l["url"]: l for l in old.get("links", [])}
    # remember first-seen dates of links that dropped off, too
    history = old.get("history", {})

    final, html = get(SOURCE)
    open("debug.html", "w", encoding="utf-8").write(html)
    found, urls = [], set()

    # 1) normal <a href> links
    p = Links(); p.feed(html)
    for it in p.items:
        url = resolve(it["href"])
        if not url or url in urls: continue
        urls.add(url)
        found.append({"url": url, "reward": reward(it["text"] + " " + it["ctx_ref"][1][:300])})

    # 2) links hidden in scripts / JSON (sites built with JavaScript)
    if not found:
        for m in re.finditer(r'https?:(?:\\?/){2}mply\.io(?:\\?/)([A-Za-z0-9_\-]{6,})', html):
            url = "https://mply.io/" + m.group(1)
            if url in urls: continue
            urls.add(url)
            ctx = re.sub(r"<[^>]+>|\\[nrt]", " ", html[max(0, m.start()-300):m.end()+300])
            found.append({"url": url, "reward": reward(ctx)})

    found = found[:MAX_LINKS]

    if not found:
        hrefs = [i["href"] for i in p.items]
        print("DEBUG final url:", final)
        print("DEBUG html size:", len(html))
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        print("DEBUG title:", t.group(1).strip() if t else None)
        print("DEBUG count 'mply':", html.count("mply"), "| 'dice':", html.lower().count("dice"))
        print("DEBUG links on page:", len(hrefs))
        for h in hrefs[:60]: print("   ", h)
    if not found:
        print("No links found - keeping previous file."); sys.exit(0)

    today = datetime.date.today().isoformat()
    for l in found:
        l["date"] = seen.get(l["url"], {}).get("date") or history.get(l["url"]) or today
        history[l["url"]] = l["date"]
    # keep history small
    history = dict(list(history.items())[-200:])

    data = {"updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "links": found, "history": history}
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(found, indent=2))

if __name__ == "__main__":
    main()
