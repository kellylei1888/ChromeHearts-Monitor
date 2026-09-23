#!/usr/bin/env python3
"""Chrome Hearts 官网上新监控。

每次运行：抓取官网所有商品分类页 -> 与上次快照对比 -> 有变化就发通知。
检测：新品上架、商品下架、价格变动、售罄、补货、新增分类。

用法：
  python3 monitor.py          # 正常运行一次
  python3 monitor.py --test   # 发送一条测试通知
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

# 官网导航里能看到的分类；运行时还会从首页导航自动发现新分类
KNOWN_CATEGORIES = [
    "/baccarat", "/scents", "/boxers-leggings", "/intimates", "/socks",
    "/underwear", "/scarf", "/on/demandware.store/Sites-ChromeHearts-Site/en_US/Search-Show?cgid=SWEATPANTS",
]
SILENT_KINDS = {"💲 改价"}  # 这些变化只记日志，不推送
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
    """官网价格有时写 "$1,650.00"，有时写 "1650.00"，统一成 "1650.00"。"""
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
        except Exception as e:  # 单个分类失败不影响其他分类
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
        changes.append(("🆕 新分类", cat, BASE + cat))
    for pid, p in new.items():
        o = old.get(pid)
        label = f"{p['name']} ${p['price']}"
        if o is None:
            changes.append(("🆕 上新", label + (" (售罄)" if p["soldout"] else ""), p["url"]))
            continue
        if norm_price(o["price"]) != p["price"]:
            changes.append(("💲 改价", f"{p['name']} ${norm_price(o['price'])} → ${p['price']}", p["url"]))
        if o["soldout"] and not p["soldout"]:
            changes.append(("✅ 补货", label, p["url"]))
        elif not o["soldout"] and p["soldout"]:
            changes.append(("⛔ 售罄", label, p["url"]))
    # 只有分类成功抓到时才判断下架，避免网络故障误报
    for pid, o in old.items():
        if pid not in new and any(o.get("_cat") == c for c in new_cats):
            changes.append(("🗑 下架", f"{o['name']} ${norm_price(o['price'])}", o["url"]))
    return changes


def notify(title, message, url=None):
    cfg = load_config()
    print(f"[notify] {title}: {message}")
    # 1) macOS 系统通知（仅在 Mac 上运行时）
    if sys.platform == "darwin" and not os.environ.get("CI"):
        script = 'display notification %s with title %s sound name "Glass"' % (
            json.dumps(message, ensure_ascii=False), json.dumps(title, ensure_ascii=False))
        subprocess.run(["osascript", "-e", script], check=False)
    # 2) 手机推送：Bark (iPhone) 或 ntfy；云端从环境变量读取
    bark = os.environ.get("BARK_URL") or cfg.get("bark_url")  # 例如 https://api.day.app/你的key
    if bark:
        q = urllib.parse.urlencode({"url": url or BASE, "group": "ChromeHearts", "level": "timeSensitive"})
        send(f"{bark.rstrip('/')}/{urllib.parse.quote(title)}/{urllib.parse.quote(message)}?{q}")
    ntfy = os.environ.get("NTFY_TOPIC") or cfg.get("ntfy_topic")  # 例如 chromehearts-xxxx
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
        notify("Chrome Hearts 监控", "测试通知：监控已正常工作 ✅", BASE)
        return

    categories, products = scrape()
    if not products:
        print("[error] 没抓到任何商品，可能网站结构变了或被拦截", file=sys.stderr)
        sys.exit(1)

    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = None

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if state is None:
        print(f"{now} 首次运行，已记录 {len(products)} 个商品 / {len(categories)} 个分类作为基准")
        notify("Chrome Hearts 监控已启动", f"已记录 {len(products)} 个商品，之后有变化会通知你")
    else:
        changes = diff(state["products"], products, state["categories"], categories)
        if changes:
            with open(LOG_FILE, "a") as f:
                for kind, text, url in changes:
                    f.write(f"{now}\t{kind}\t{text}\t{url}\n")
            # 改价只记录到 changes.log，不推送
            pushes = [c for c in changes if c[0] not in SILENT_KINDS]
            for kind, text, url in pushes[:5]:
                notify(f"Chrome Hearts {kind}", text, url)
            if len(pushes) > 5:
                notify("Chrome Hearts", f"另有 {len(pushes) - 5} 项变化，详见 changes.log")
            print(f"{now} 发现 {len(changes)} 项变化")
        else:
            print(f"{now} 无变化（{len(products)} 个商品）")

    with open(STATE_FILE, "w") as f:
        json.dump({"checked_date": now[:10], "categories": sorted(set(categories) | set((state or {}).get("categories", []))), "products": products},
                  f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
