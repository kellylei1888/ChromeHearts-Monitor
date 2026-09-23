#!/usr/bin/env python3
"""Chrome Hearts ÂÆòÁΩë‰∏äÊñ∞ÁõëÊéß„ÄÇ

ÊØèÊ¨°ËøêË°åÔºöÊäìÂèñÂÆòÁΩëÊâÄÊúâÂïÜÂìÅÂàÜÁ±ªÈ°µ -> ‰∏é‰∏äÊ¨°Âø´ÁÖßÂØπÊØî -> ÊúâÂèòÂåñÂ∞±ÂèëÈÄöÁü•„ÄÇ
Ê£ÄÊµãÔºöÊñ∞ÂìÅ‰∏äÊû∂„ÄÅÂïÜÂìÅ‰∏ãÊû∂„ÄÅ‰ª∑Ê†ºÂèòÂä®„ÄÅÂîÆÁΩÑ„ÄÅË°•Ë¥ß„ÄÅÊñ∞Â¢ûÂàÜÁ±ª„ÄÇ

Áî®Ê≥ïÔºö
  python3 monitor.py          # Ê≠£Â∏∏ËøêË°å‰∏ÄÊ¨°
  python3 monitor.py --test   # ÂèëÈÄÅ‰∏ÄÊù°ÊµãËØïÈÄöÁü•
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape

BASE = "https://www.chromehearts.com"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")
LOG_FILE = os.path.join(HERE, "changes.log")
CONFIG_FILE = os.path.join(HERE, "config.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# ÂÆòÁΩëÂØºËà™ÈáåËÉΩÁúãÂà∞ÁöÑÂàÜÁ±ªÔºõËøêË°åÊó∂Ëøò‰ºö‰ªéÈ¶ñÈ°µÂØºËà™Ëá™Âä®ÂèëÁé∞Êñ∞ÂàÜÁ±ª
KNOWN_CATEGORIES = [
    "/baccarat", "/scents", "/boxers-leggings", "/intimates", "/socks",
    "/underwear", "/scarf", "/on/demandware.store/Sites-ChromeHearts-Site/en_US/Search-Show?cgid=SWEATPANTS",
]
SILENT_KINDS = {"üí≤ Êîπ‰ª∑"}  # Ëøô‰∫õÂèòÂåñÂè™ËÆ∞Êó•ÂøóÔºå‰∏çÊé®ÈÄÅ
NON_CATEGORY = {"/", "/cart", "/login", "/contact", "/shop", "/#", ""}


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def fetch(path):
    url = path if path.startswith("http") else BASE + path
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def discover_categories(home_html):
    cats = set(KNOWN_CATEGORIES)
    for href in re.findall(r'href="(?:https://www\.chromehearts\.com)?(/[^"#]*)"', home_html):
        href = unescape(href)
        if href in NON_CATEGORY or href.endswith(".html") or "demandware.static" in href:
            continue
        if "Search-Show?cgid=" in href or re.fullmatch(r"/[a-z0-9-]+", href):
            cats.add(href)
    return sorted(cats)


def norm_price(p):
    """ÂÆòÁΩë‰ª∑Ê†ºÊúâÊó∂ÂÜô "$1,650.00"ÔºåÊúâÊó∂ÂÜô "1650.00"ÔºåÁªü‰∏ÄÊàê "1650.00"„ÄÇ"""
    p = p.replace("$", "").replace(",", "").strip()
    try:
        return "%.2f" % float(p)
    except ValueError:
        return p


def parse_products(html, category):
    products = {}
    soldout = set(re.findall(r'class="soldout"[^>]*href="[^"]*/([^/"]+)\.html', html))
    for m in re.finditer(r'<span class="product-metadata[^"]*"(.*?)>', html, re.S):
        attrs = {k: unescape(v) for k, v in re.findall(r'data-([\w-]+)="([^"]*)"', m.group(1))}
        pid = attrs.get("pid")
        if not pid:
            continue
        link = re.search(r'href="([^"]*/%s\.html)' % re.escape(pid), html)
        products[pid] = {
            "name": attrs.get("name", "").strip(),
            "price": norm_price(attrs.get("price", "")),
            "category": attrs.get("category") or category,
            "soldout": pid in soldout,
            "url": urllib.parse.urljoin(BASE, unescape(link.group(1))) if link else BASE + category,
        }
    return products


def scrape():
    home = fetch("/")
    categories = discover_categories(home)
    products, ok_cats = {}, []
    for cat in categories:
        try:
            html = fetch(cat)
        except Exception as e:  # Âçï‰∏™ÂàÜÁ±ªÂ§±Ë¥•‰∏çÂΩ±ÂìçÂÖ∂‰ªñÂàÜÁ±ª
            print(f"[warn] {cat}: {e}", file=sys.stderr)
            continue
        ok_cats.append(cat)
        for pid, p in parse_products(html, cat).items():
            p["_cat"] = cat
            products.setdefault(pid, p)
        time.sleep(1)
    return ok_cats, products


def diff(old, new, old_cats, new_cats):
    changes = []
    for cat in sorted(set(new_cats) - set(old_cats)):
        changes.append(("üÜï Êñ∞ÂàÜÁ±ª", cat, BASE + cat))
    for pid, p in new.items():
        o = old.get(pid)
        label = f"{p['name']} ${p['price']}"
        if o is None:
            changes.append(("üÜï ‰∏äÊñ∞", label + (" (ÂîÆÁΩÑ)" if p["soldout"] else ""), p["url"]))
            continue
        if norm_price(o["price"]) != p["price"]:
            changes.append(("üí≤ Êîπ‰ª∑", f"{p['name']} ${norm_price(o['price'])} ‚Üí ${p['price']}", p["url"]))
        if o["soldout"] and not p["soldout"]:
            changes.append(("‚úÖ Ë°•Ë¥ß", label, p["url"]))
        elif not o["soldout"] and p["soldout"]:
            changes.append(("‚õî ÂîÆÁΩÑ", label, p["url"]))
    # Âè™ÊúâÂàÜÁ±ªÊàêÂäüÊäìÂà∞Êó∂ÊâçÂà§Êñ≠‰∏ãÊû∂ÔºåÈÅøÂÖçÁΩëÁªúÊïÖÈöúËØØÊä•
    for pid, o in old.items():
        if pid not in new and any(o.get("_cat") == c for c in new_cats):
            changes.append(("üóë ‰∏ãÊû∂", f"{o['name']} ${norm_price(o['price'])}", o["url"]))
    return changes


def notify(title, message, url=None):
    cfg = load_config()
    print(f"[notify] {title}: {message}")
    # 1) macOS Á≥ªÁªüÈÄöÁü•Ôºà‰ªÖÂú® Mac ‰∏äËøêË°åÊó∂Ôºâ
    if sys.platform == "darwin" and not os.environ.get("CI"):
        script = 'display notification %s with title %s sound name "Glass"' % (
            json.dumps(message, ensure_ascii=False), json.dumps(title, ensure_ascii=False))
        subprocess.run(["osascript", "-e", script], check=False)
    # 2) ÊâãÊú∫Êé®ÈÄÅÔºöBark (iPhone) Êàñ ntfyÔºõ‰∫ëÁ´Ø‰ªéÁéØÂ¢ÉÂèòÈáèËØªÂèñ
    bark = os.environ.get("BARK_URL") or cfg.get("bark_url")  # ‰æãÂ¶Ç https://api.day.app/‰Ω†ÁöÑkey
    if bark:
        q = urllib.parse.urlencode({"url": url or BASE, "group": "ChromeHearts", "level": "timeSensitive"})
        send(f"{bark.rstrip('/')}/{urllib.parse.quote(title)}/{urllib.parse.quote(message)}?{q}")
    ntfy = os.environ.get("NTFY_TOPIC") or cfg.get("ntfy_topic")  # ‰æãÂ¶Ç chromehearts-xxxx
    if ntfy:
        req = urllib.request.Request(
            f"https://ntfy.sh/{ntfy}", data=message.encode(),
            headers={"Title": title.encode("utf-8").decode("latin-1", "ignore") or "Chrome Hearts",
                     "Click": url or BASE})
        send(req)


def send(req):
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print(f"[warn] push failed: {e}", file=sys.stderr)


def main():
    if "--test" in sys.argv:
        notify("Chrome Hearts ÁõëÊéß", "ÊµãËØïÈÄöÁü•ÔºöÁõëÊéßÂ∑≤Ê≠£Â∏∏Â∑•‰Ωú ‚úÖ", BASE)
        return

    categories, products = scrape()
    if not products:
        print("[error] Ê≤°ÊäìÂà∞‰ªª‰ΩïÂïÜÂìÅÔºåÂèØËÉΩÁΩëÁ´ôÁªìÊûÑÂèò‰∫ÜÊàñË¢´Êã¶Êà™", file=sys.stderr)
        sys.exit(1)

    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = None

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if state is None:
        print(f"{now} È¶ñÊ¨°ËøêË°åÔºåÂ∑≤ËÆ∞ÂΩï {len(products)} ‰∏™ÂïÜÂìÅ / {len(categories)} ‰∏™ÂàÜÁ±ª‰Ωú‰∏∫Âü∫ÂáÜ")
        notify("Chrome Hearts ÁõëÊéßÂ∑≤ÂêØÂä®", f"Â∑≤ËÆ∞ÂΩï {len(products)} ‰∏™ÂïÜÂìÅÔºå‰πãÂêéÊúâÂèòÂåñ‰ºöÈÄöÁü•‰Ω†")
    else:
        changes = diff(state["products"], products, state["categories"], categories)
        if changes:
            with open(LOG_FILE, "a") as f:
                for kind, text, url in changes:
                    f.write(f"{now}\t{kind}\t{text}\t{url}\n")
            # Êîπ‰ª∑Âè™ËÆ∞ÂΩïÂà∞ changes.logÔºå‰∏çÊé®ÈÄÅ
            pushes = [c for c in changes if c[0] not in SILENT_KINDS]
            for kind, text, url in pushes[:5]:
                notify(f"Chrome Hearts {kind}", text, url)
            if len(pushes) > 5:
                notify("Chrome Hearts", f"Âè¶Êúâ {len(pushes) - 5} È°πÂèòÂåñÔºåËØ¶ËßÅ changes.log")
            print(f"{now} ÂèëÁé∞ {len(changes)} È°πÂèòÂåñ")
        else:
            print(f"{now} Êó†ÂèòÂåñÔºà{len(products)} ‰∏™ÂïÜÂìÅÔºâ")

    with open(STATE_FILE, "w") as f:
        json.dump({"checked_date": now[:10], "categories": sorted(set(categories) | set((state or {}).get("categories", []))), "products": products},
                  f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
