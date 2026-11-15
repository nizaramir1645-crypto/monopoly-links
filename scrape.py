"""Fetch Monopoly GO reward links from monopolygo.wiki and save the newest ones to links.json.
Only the official mply.io links + reward amount are kept (no text is copied)."""
import json, re, sys, datetime, urllib.request, urllib.error, urllib.parse
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

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None

def next_hop(url):
    """Return the Location of one redirect step (without following it)."""
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        r = opener.open(req, timeout=20)
        body = r.read(20000).decode("utf-8", "ignore")
        m = re.search(r'https?://mply\.io/[A-Za-z0-9_\-]+', body)   # JS / meta refresh redirect
        return m.group(0) if m else None
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
        return urllib.parse.urljoin(url, loc) if loc else None
    except Exception:
        return None

def resolve(href):
    """Return the official mply.io URL (follows the site's own short links step by step)."""
    if "mply.io" in href:
        return href.split("?")[0]
    if re.search(r"mplygo\.wiki/", href):
        url = href
        for _ in range(5):
            url = next_hop(url)
            if not url: break
            if "mply.io" in url: return url.split("?")[0]
        print("WARN could not resolve", href)
    return None

def reward(text):
    t = " ".join(text.split())
    m = re.search(r"(\d{2,4})\s*(?:free\s*)?(?:dice|rolls?)", t, re.I)
    if m: return f"{m.group(1)} Free Dice Rolls"
    for w in ("sticker", "token", "cash", "shield"):
        if w in t.lower(): return "Free " + w.capitalize() + " Reward"
    return "Free Dice Rolls"

def reward_near(html, href, fallback):
    """Look at the text just before/after the link in the page to find '25 dice' etc."""
    r = reward(fallback)
    if r != "Free Dice Rolls": return r
    i = html.find(href)
    if i < 0: return r
    def clean(t): return " ".join(re.sub(r"<[^>]+>", " ", t).split())
    after, before = clean(html[i:i+800]), clean(html[max(0, i-800):i])
    for t in (after[:200], before[-200:], after, before):
        x = reward(t)
        if x != "Free Dice Rolls": return x
    return r

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
        found.append({"url": url, "reward": reward_near(html, it["href"], it["text"] + " " + it["ctx_ref"][1][:300])})

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

    data = {"updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "links": found, "history": history}
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(found, indent=2))

if __name__ == "__main__":
    main()
