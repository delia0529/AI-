"""
历史补录 —— 用可回溯的数据源补齐断更日期的「简版日报」

可用（支持按日期查询历史）：
  - Hacker News Algolia API：search_by_date + created_at_i 区间，可精确到任意历史日期
  - Hugging Face Papers：/papers/date/<YYYY-MM-DD> 当日论文归档

不可用（没有历史接口，不要假装能取）：
  - GitHub Trending（只有「今天/本周/本月」的相对榜）
  - Techmeme / TechCrunch / FT / 量子位 等 RSS（只保留最近 24–48 小时）

产出：data/<date>.json，带 backfill 标记，页面会显示「补录 · 数据源有限」徽标。
每期只收录当日 HN 高票条目 + 当日 HF 论文，5–8 条，不做虚构的深度解读。

用法：
  python3 scripts/backfill.py --start 2026-09-25 --end 2026-10-09
  python3 scripts/backfill.py --start 2026-09-25 --end 2026-10-09 --min-points 60
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
UA = "ai-daily-digest/1.0 (+https://github.com/delia0529/AI-)"

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 模块归属关键词（按顺序匹配）
MODULE_RULES = [
    ("china", ["qwen", "deepseek", "alibaba", "tencent", "bytedance", "xiaomi", "moonshot",
               "kimi", "zhipu", "glm", "mimo", "huawei", "chinese lab", "china"]),
    ("browser", ["browser", "chrome", "chromium", "edge ", "firefox", "safari", "extension",
                 "on-device", "local llm", "apple silicon", "webassembly", "webgpu"]),
    ("macro", ["regulation", "regulator", "policy", "lawsuit", "sue ", "court", "eu ",
               "european", "antitrust", "ban ", "government", "trump", "ipo", "bond",
               "data center", "datacenter", "nvidia ", "chip", "tsmc", "sanction"]),
    ("frontier", ["llm", "model", "gpt", "claude", "gemini", "agent", "rag", "inference",
                  "training", "benchmark", "token", "prompt", "embedding", "fine-tun",
                  "rl ", "reinforcement", "openai", "anthropic"]),
]

TOPIC_LABEL = {
    "china": "国内厂商与生态",
    "browser": "浏览器 / 端侧工作流",
    "macro": "政策、资本与算力供给",
    "frontier": "模型与 Agent 技术",
}


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_hn(day_start, day_end, min_points):
    query = urllib.parse.urlencode({
        "tags": "story",
        "numericFilters": "created_at_i>%d,created_at_i<%d,points>%d" % (day_start, day_end, min_points),
        "hitsPerPage": 60,
    })
    url = "https://hn.algolia.com/api/v1/search_by_date?%s" % query
    try:
        payload = json.loads(http_get(url))
    except Exception as exc:
        print("  ! HN 抓取失败：%s" % exc)
        return []
    out = []
    for hit in payload.get("hits", []):
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        url2 = hit.get("url") or ("https://news.ycombinator.com/item?id=%s" % hit.get("objectID"))
        out.append({
            "title": title,
            "url": url2,
            "points": hit.get("points") or 0,
            "comments": hit.get("num_comments") or 0,
            "source": "Hacker News",
            "created": hit.get("created_at", ""),
        })
    return out


def fetch_hf_papers(date_str):
    url = "https://huggingface.co/papers/date/%s" % date_str
    try:
        html = http_get(url)
    except Exception:
        return []
    seen = []
    for m in re.finditer(r'href="(/papers/\d+\.\d+)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{12,180}?)\s*<', html):
        title = m.group(2).strip()
        if title and title not in seen:
            seen.append((title, "https://huggingface.co%s" % m.group(1)))
    return seen[:2]


def classify(title):
    low = title.lower()
    for mod, keys in MODULE_RULES:
        for k in keys:
            if k in low:
                return mod
    return "frontier"


def domain_of(url):
    return urllib.parse.urlparse(url).netloc.replace("www.", "")


def build_issue(date_str, hn_items, papers, issue_no):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    grouped = {}

    for it in hn_items:
        mod = classify(it["title"])
        grouped.setdefault(mod, []).append({
            "title": it["title"],
            "category": TOPIC_LABEL[mod],
            "priority": "high" if it["points"] >= 150 else "mid",
            "facts": "Hacker News %s 的当日条目：%s。讨论热度 %d 分、%d 条评论；出处 %s。" % (
                date_str, it["title"], it["points"], it["comments"], domain_of(it["url"])),
            "insight": "该条属于%s方向，当日获得 %d 分讨论。补录期仅收录条目与热度，未做二次解读，结论请以原文为准。" % (
                TOPIC_LABEL[mod], it["points"]),
            "entities": [domain_of(it["url"])],
            "tags": ["#补录"] + (["#大厂战略"] if mod == "macro" else
                                ["#端侧AI"] if mod == "browser" else
                                ["#大厂战略"] if mod == "china" else ["#模型架构"]),
            "sources": [{"name": "%s · %s" % (it["source"], it["title"][:40]), "url": it["url"]}],
        })

    for title, link in papers:
        grouped.setdefault("frontier", []).append({
            "title": title,
            "category": "论文",
            "priority": "mid",
            "facts": "Hugging Face %s 当日论文归档中的条目：%s。" % (date_str, title),
            "insight": "当日论文收录，补录期仅记录题名与链接，具体结论以论文原文为准。",
            "entities": ["huggingface.co"],
            "tags": ["#补录", "#论文"],
            "sources": [{"name": "Hugging Face Papers", "url": link}],
        })

    modules_def = [
        ("macro", "01", "全球 AI 宏观与政经脉搏", "MACRO & POLICY"),
        ("browser", "02", "AI 浏览器与端侧工作流", "BROWSER & EDGE WORKFLOW"),
        ("china", "03", "国内三巨头与本土生态", "CHINA BIG THREE"),
        ("frontier", "04", "前沿模型与落地产品", "FRONTIER & PRODUCT"),
    ]

    modules = []
    for key, index, name, en in modules_def:
        items = grouped.get(key, [])
        if not items:
            continue
        modules.append({
            "id": key,
            "index": index,
            "name": name,
            "en": en,
            "note": "补录期：仅收录当日可回溯条目，未做深度整合。",
            "watchlist": [],
            "items": items[:6],
        })

    if not modules:
        return None

    total = sum(len(m["items"]) for m in modules)
    return {
        "date": date_str,
        "issue": "No.%03d" % issue_no,
        "weekday": WEEKDAY_CN[dt.weekday()],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M CST"),
        "window": "%s 00:00 → 24:00 UTC" % date_str,
        "headline": "补录 · %s 当日可回溯条目" % date_str,
        "deck": "本期为断更补录，数据源仅限 Hacker News 历史条目与 Hugging Face 当日论文归档（GitHub Trending 与 RSS 源无历史接口，无法回溯）。共 %d 条，只记录条目与热度，不含深度解读，可信度低于常规期次。" % total,
        "stats": {
            "sources": 2,
            "raw": len(hn_items) + len(papers),
            "items": total,
            "clusters": total,
            "dedupe_rate": "—",
        },
        "backfill": True,
        "backfill_note": "补录期 · 数据源有限（HN 历史 + HF 论文），仅供参考",
        "modules": modules,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--min-points", type=int, default=40, help="HN 最低分数门槛")
    ap.add_argument("--start-issue", type=int, default=None, help="起始期号")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")

    # 期号：接在现有期次后面
    existing = sorted(f[:10] for f in os.listdir(DATA_DIR) if re.match(r"^\d{4}-\d{2}-\d{2}\.json$", f))
    issue_no = args.start_issue or (len(existing) + 1)

    made = []
    d = start
    while d <= end:
        date_str = d.strftime("%Y-%m-%d")
        if os.path.exists(os.path.join(DATA_DIR, "%s.json" % date_str)):
            print("- %s 已存在，跳过" % date_str)
            d += timedelta(days=1)
            continue

        day_start = int(d.replace(tzinfo=timezone.utc).timestamp())
        day_end = int((d + timedelta(days=1)).replace(tzinfo=timezone.utc).timestamp())

        hn = fetch_hn(day_start, day_end, args.min_points)
        papers = fetch_hf_papers(date_str)
        # 同一域名只保留最高分的一条，避免刷屏
        by_domain = {}
        for it in sorted(hn, key=lambda x: -x["points"]):
            dm = domain_of(it["url"])
            by_domain.setdefault(dm, it)
        picked = sorted(by_domain.values(), key=lambda x: -x["points"])[:6]

        issue = build_issue(date_str, picked, papers, issue_no)
        if issue:
            path = os.path.join(DATA_DIR, "%s.json" % date_str)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(issue, fh, ensure_ascii=False, indent=2)
            print("✓ %s  No.%03d  %d 条（HN %d / 论文 %d）" % (
                date_str, issue_no, issue["stats"]["items"], len(picked), len(papers)))
            made.append(date_str)
            issue_no += 1
        else:
            print("- %s 无可用条目，跳过" % date_str)

        d += timedelta(days=1)
        time.sleep(0.4)

    print("\n补录完成：%d 期 → %s" % (len(made), ", ".join(made) if made else "无"))


if __name__ == "__main__":
    sys.exit(main())
