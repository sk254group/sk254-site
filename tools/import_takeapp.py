"""Scrape the SK254 Take.app store into public/admin/takeapp-import.json.

Usage:  python -I tools/import_takeapp.py
The admin panel (Settings > Import from Take.app) reads that JSON and merges it
into the live store. Product photos stay on Take.app's CDN until the admin
"Copy photos from Take.app" button moves them into Cloudflare KV.
"""
import concurrent.futures as cf
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

STORE = "https://take.app/sk254"
OUT = Path(__file__).resolve().parent.parent / "public" / "admin" / "takeapp-import.json"
SKIP_CATS = {"SIZE GUIDELINES", "Book a Turf!"}
RENAME = {"epl": "Premier League", "ligue1": "Ligue 1", "kids-youth": "Kids / Youth"}
FEATURED = {"cmeu0b2bt000xih04zhhh0agw", "cmeprz7jy0001l204u8gfelc1", "cmftoog54000vl904zxkhbis9", "cmglzysl8004pl804v5p637mj"}
ADULT = ["XS", "S", "SMALL", "M", "MEDIUM", "L", "LARGE", "XL", "XXL", "2XL", "3XL", "4XL", "5XL"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SK254 store migration)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def text_of(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).strip()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean_cat(name):
    name = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", name)
    name = name.replace("Official Licensed F1 Jerseys", "").replace("Your ideas professionally crafted by SK254", "")
    return name.strip()


def sort_sizes(sizes):
    if all(s.upper() in ADULT for s in sizes):
        return sorted(sizes, key=lambda s: ADULT.index(s.upper()))
    nums = [re.match(r"S(\d+)", s) for s in sizes]
    if all(nums):
        return [s for _, s in sorted(zip([int(m.group(1)) for m in nums], sizes))]
    return sizes


def product(pid, cats):
    page = get(f"{STORE}/p/{pid}")
    group = None
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if data.get("@type") in ("ProductGroup", "Product"):
            group = data
            break
    if not group:
        return None
    name = group["name"].strip()
    variants = group.get("hasVariant") or [group]
    sizes = [v["name"].replace(name, "", 1).lstrip(" -").strip() for v in variants] if group.get("hasVariant") else []
    sizes = sort_sizes([re.sub(r"^Adult\s+", "", s, flags=re.I) for s in sizes if s]) or ["One size"]
    prices = [float(v.get("offers", {}).get("price", 0)) for v in variants]
    prices = [int(p) for p in prices if p > 0]
    out = all("InStock" not in v.get("offers", {}).get("availability", "") for v in variants)
    imgs = []
    for v in variants + [group]:
        for u in v.get("image", []):
            u = u.replace("https://storage.googleapis.com/takeapp/media/", "https://cdn3.take.app/media/") + "?width=1200"
            if u not in imgs:
                imgs.append(u)
    price = min(prices) if prices else 0
    head = text_of(page.split("You may also like")[0])
    m = re.search(r"Ksh\s*([\d,]+)\.00\s+Ksh\s*([\d,]+)\.00", head)
    was = None
    if m:
        a, b = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
        was = b if b > a else None
    c = cats
    if re.search(r"\bPV\b|player", name, re.I) or "player-version" in c:
        label = "Player Version"
    elif "kids-youth" in c or re.search(r"kids", name, re.I):
        label = "Kids"
    elif "formula-1" in c:
        label = "Formula 1"
    elif "rugby" in c:
        label = "Rugby"
    elif "cricket" in c:
        label = "Cricket"
    elif "custom-prints" in c:
        label = "Custom Print"
    elif re.search(r"fan", name, re.I) or "fan-kits" in c:
        label = "Fan Version"
    else:
        label = RENAME.get(c[0], c[0].replace("-", " ").title())
    return {
        "id": "t" + pid[-10:], "name": name, "label": label, "price": price, "was": was,
        "imgs": imgs[:6], "cats": c, "sizes": sizes, "out": out, "hidden": False,
        "featured": pid in FEATURED, "src": "takeapp:" + pid,
    }


def main():
    home = get(STORE)
    links = re.findall(r'href="(?:https://take.app)?/sk254/c/([a-z0-9]+)"[^>]*>(.*?)</a>', home, re.S)
    cat_list, members = [], {}
    seen = set()
    for cid, inner in links:
        if cid in seen:
            continue
        seen.add(cid)
        name = clean_cat(text_of(inner))
        if not name or name in SKIP_CATS:
            continue
        ids = list(dict.fromkeys(re.findall(r"/sk254/p/([a-z0-9]+)", get(f"{STORE}/c/{cid}"))))
        if not ids:
            continue
        key = slug(name)
        if key not in [c["id"] for c in cat_list]:
            pretty = RENAME.get(key) or (name.title() if name.isupper() else name)
            cat_list.append({"id": key, "name": pretty})
        for pid in ids:
            members.setdefault(pid, []).append(key) if key not in members.get(pid, []) else None
    with cf.ThreadPoolExecutor(6) as ex:
        prods = [p for p in ex.map(lambda pid: product(pid, members[pid]), members) if p]
    OUT.write_text(json.dumps({"categories": cat_list, "products": prods}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(prods)} products, {len(cat_list)} categories -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
