"""
数据抓取层 —— 流水线第 1 段：06:00 - 07:30

零第三方依赖（仅标准库）。支持四类源：
  rss            通用 RSS / Atom
  hn_api         Hacker News（Algolia 官方 API）
  github_trending GitHub Trending 页面抓取
  hf_papers      Hugging Face Daily Papers 页面抓取

输出： data/raw/<date>.json  —— [{title, url, source, published, summary}]

用法：
  python3 scripts/fetch_sources.py                 # 抓最近 24 小时
  python3 scripts/fetch_sources.py --hours 36 --date 2026-09-17
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
UA = "ai-daily-digest/1.0 (+https://github.com/your-org/ai-daily-digest)"


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


# ------------------------------------------------------------------ parsers

def parse_rss(xml_text, source_id):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for node in nodes:
        def pick(*names):
            for n in names:
                el = node.find(n)
                if el is not None and (el.text or el.get("href")):
                    return (el.text or el.get("href")).strip()
            return ""

        link = pick("link", "{http://www.w3.org/2005/Atom}link")
        if not link:
            for el in node.findall("{http://www.w3.org/2005/Atom}link"):
                link = el.get("href") or ""
                if link:
                    break
        published = pick("pubDate", "published", "{http://www.w3.org/2005/Atom}published",
                         "{http://www.w3.org/2005/Atom}updated")
        items.append({
            "title": pick("title", "{http://www.w3.org/2005/Atom}title"),
            "url": link,
            "source": source_id,
            "published": published,
            "summary": re.sub(r"<[^>]+>", "", pick("description", "summary",
                                                   "{http://www.w3.org/2005/Atom}summary"))[:600],
            "points": 0,
        })
    return items


def parse_hn_api(payload, source_id):
    items = []
    for hit in payload.get("hits", []):
        title = hit.get("title") or hit.get("story_title")
        url = hit.get("url") or ("https://news.ycombinator.com/item?id=%s" % hit.get("objectID"))
        if not title:
            continue
        items.append({
            "title": title,
            "url": url,
            "source": source_id,
            "published": hit.get("created_at", ""),
            "summary": (hit.get("story_text") or "")[:600],
            "points": hit.get("points") or 0,
        })
    return items


def parse_github_trending(html, source_id):
    items = []
    blocks = re.findall(r'<article class="Box-row">(.*?)</article>', html, re.S)
    for b in blocks:
        m = re.search(r'<h2[^>]*>\s*<a\s[^>]*?href="/([^"]+)"', b)
        if not m:
            continue
        repo = m.group(1)
        desc = re.search(r'<p class="col-9 color-fg-muted my-1 pr-4">\s*(.*?)\s*</p>', b, re.S)
        stars = re.search(r'([\d,]+)\s*stars today', b)
        items.append({
            "title": "%s — %s" % (repo, (desc.group(1).strip() if desc else "GitHub Trending")),
            "url": "https://github.com/%s" % repo,
            "source": source_id,
            "published": datetime.now(timezone.utc).isoformat(),
            "summary": "单日新增 %s stars" % (stars.group(1) if stars else "N/A"),
            "points": int((stars.group(1) if stars else "0").replace(",", "") or 0),
        })
    return items


def parse_hf_papers(html, source_id):
    items = []
    for m in re.finditer(r'<a[^>]+href="(/papers/\d+\.\d+)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{10,200}?)\s*</a>', html):
        items.append({
            "title": m.group(2).strip(),
            "url": "https://huggingface.co%s" % m.group(1),
            "source": source_id,
            "published": datetime.now(timezone.utc).isoformat(),
            "summary": "Hugging Face Daily Papers",
            "points": 0,
        })
        if len(items) >= 20:
            break
    return items


PARSERS = {
    "rss": parse_rss,
    "hn_api": parse_hn_api,
    "github_trending": parse_github_trending,
    "hf_papers": parse_hf_papers,
}


# ------------------------------------------------------------------ fetch

def fetch_source(cfg, since_ts, cutoff):
    sid, kind, url = cfg["id"], cfg["type"], cfg["url"]
    try:
        if kind == "hn_api":
            query = urllib.parse.urlencode({
                "tags": "story",
                "numericFilters": "created_at_i>%d,points>40" % since_ts,
                "hitsPerPage": 60,
            })
            payload = json.loads(http_get("%s&%s" % (url, query)))
            items = PARSERS[kind](payload, sid)
        else:
            items = PARSERS[kind](http_get(url), sid)
    except Exception as exc:  # 单个源失败不能中断整条流水线
        print("  ! %-16s 抓取失败：%s" % (sid, exc))
        return []

    kept = []
    for it in items:
        if not it.get("title") or not it.get("url"):
            continue
        ts = to_ts(it.get("published"))
        if ts and ts < cutoff:
            continue
        it["_ts"] = ts or int(time.time())
        it["weight"] = cfg.get("weight", 1.0)
        kept.append(it)
    print("  ✓ %-16s %d 条" % (sid, len(kept)))
    return kept


def to_ts(value):
    if not value:
        return 0
    try:
        return int(parsedate_to_datetime(value).timestamp())
    except Exception:
        pass
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--hours", type=int, default=24, help="回溯窗口（小时）")
    args = ap.parse_args()

    config = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    now = int(time.time())
    cutoff = now - args.hours * 3600

    print("[fetch] 窗口：最近 %d 小时" % args.hours)
    all_items, seen = [], set()
    for cfg in config["sources"]:
        for it in fetch_source(cfg, cutoff, cutoff):
            key = re.sub(r"\W+", "", it["url"].split("?")[0]).lower()
            if key in seen:
                continue
            seen.add(key)
            all_items.append(it)

    all_items.sort(key=lambda x: (x["weight"] * 100 + x.get("points", 0)), reverse=True)
    os.makedirs(RAW_DIR, exist_ok=True)
    out = os.path.join(RAW_DIR, "%s.json" % args.date)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"date": args.date, "fetched_at": datetime.now().isoformat(timespec="seconds"),
                   "items": all_items}, fh, ensure_ascii=False, indent=2)
    print("[fetch] 共 %d 条 → %s" % (len(all_items), os.path.relpath(out, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
