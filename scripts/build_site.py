"""
静态站点生成（SSG）——流水线第 3 段：08:15 - 08:45

职责：
  1. 扫描 data/*.json，重建 data/index.json（历期元数据，供前端检索）
  2. 用 templates/daily.html 渲染 index.html（永远指向最新一期）与 archive/<date>.html（历史快照）
  3. 用 templates/archive.html 渲染 archive.html（历史档案总览）
  4. 把 templates/partials.* 落地为 assets/style.css 与 assets/app.js

用法：
  python3 scripts/build_site.py              # 渲染全部期次
  python3 scripts/build_site.py --latest     # 只渲染最新一期 + 首页 + 归档页
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from template_engine import render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
TPL_DIR = os.path.join(ROOT, "templates")
ARCHIVE_DIR = os.path.join(ROOT, "archive")
ASSET_DIR = os.path.join(ROOT, "assets")

PRIORITY_LABEL = {"high": "高优先", "mid": "常规", "low": "观察"}
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------------------------------------------------------------- utils

def esc(value):
    """HTML 转义，避免内容里出现 < & > 破坏结构。"""
    if value is None:
        return ""
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def weekday_of(date_str):
    try:
        return WEEKDAY_CN[datetime.strptime(date_str, "%Y-%m-%d").weekday()]
    except ValueError:
        return ""


def date_cn(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return "%d年%d月%d日 · %s" % (dt.year, dt.month, dt.day, WEEKDAY_CN[dt.weekday()])
    except ValueError:
        return date_str


# ---------------------------------------------------------------- context

def collect_issue_meta(day):
    """从当天 JSON 抽取写入 data/index.json 的元数据。"""
    tags = []
    items = 0
    for module in day.get("modules", []):
        for item in module.get("items", []):
            items += 1
            for tag in item.get("tags", []):
                if tag not in tags:
                    tags.append(tag)
    return {
        "date": day["date"],
        "issue": day.get("issue", ""),
        "weekday": day.get("weekday") or weekday_of(day["date"]),
        "headline": day.get("headline", ""),
        "deck": day.get("deck", ""),
        "items": items,
        "sources": day.get("stats", {}).get("sources", 0),
        "clusters": day.get("stats", {}).get("clusters", 0),
        "url": "archive/%s.html" % day["date"],
        "data": "data/%s.json" % day["date"],
        "tags": tags,
    }


def build_issue_context(day, issues, base):
    """渲染一期日报所需的完整上下文。"""
    stats = day.get("stats", {})
    modules = []
    cloud = []

    for module in day.get("modules", []):
        items = []
        for i, item in enumerate(module.get("items", []), start=1):
            tags = item.get("tags", [])
            for tag in tags:
                if tag not in cloud:
                    cloud.append(tag)
            items.append({
                "item_id": item.get("id", "%s-%d" % (module.get("id", "m"), i)),
                "item_no": "%s·%02d" % (module.get("index", "00"), i),
                "item_title": esc(item.get("title", "")),
                "item_cat": esc(item.get("category", "")),
                "item_prio": item.get("priority", "mid"),
                "item_prio_label": PRIORITY_LABEL.get(item.get("priority", "mid"), "常规"),
                "item_facts": esc(item.get("facts", "")),
                "item_insight": esc(item.get("insight", "")),
                "item_entities": esc("、".join(item.get("entities", []))),
                "item_tags_attr": "|".join(tags),
                "tags": [{"tag_name": esc(t)} for t in tags],
                "sources": [{"src_name": esc(s.get("name", "")), "src_url": esc(s.get("url", ""))}
                            for s in item.get("sources", [])],
                # 配图只允许来自厂商官网 / 第三方真实截图，禁止 AI 生成图
                "images": [{"img_url": esc(im.get("url", "")),
                            "img_caption": esc(im.get("caption", "")),
                            "img_credit": esc(im.get("credit", "")),
                            "img_link": esc(im.get("link") or im.get("url", ""))}
                           for im in item.get("images", []) if im.get("url")],
            })
        modules.append({
            "module_id": module.get("id", "module"),
            "module_index": module.get("index", "00"),
            "module_name": esc(module.get("name", "")),
            "module_en": esc(module.get("en", "")),
            "module_note": esc(module.get("note", "")),
            "items": items,
            "watch": [{"watch_k": esc(w.get("k", "")), "watch_v": esc(w.get("v", ""))}
                      for w in module.get("watchlist", [])],
        })

    # 本期信源清单：把当天所有引用去重汇总，保证每条内容都可追溯
    src_map = {}
    for module in modules:
        for item in module["items"]:
            for s in item["sources"]:
                key = s["src_url"]
                if key not in src_map:
                    src_map[key] = {
                        "src_index_name": esc(s["src_name"]),
                        "src_index_url": esc(s["src_url"]),
                        "src_index_domain": esc(urllib.parse.urlparse(s["src_url"]).netloc.replace("www.", "")),
                        "src_index_count": 0,
                    }
                src_map[key]["src_index_count"] += 1
    sources_index = sorted(src_map.values(), key=lambda x: (-x["src_index_count"], x["src_index_domain"]))

    return {
        "BASE": base,
        "LIVE": "1" if base == "" else "0",
        "DATE": day["date"],
        "sources_index": sources_index,
        "DATE_CN": date_cn(day["date"]),
        "ISSUE": day.get("issue", ""),
        "WEEKDAY": day.get("weekday") or weekday_of(day["date"]),
        "WINDOW": esc(day.get("window", "")),
        "GENERATED": esc(day.get("generated_at", "")),
        "HEADLINE": esc(day.get("headline", "")),
        "DECK": esc(day.get("deck", "")),
        "STAT_SOURCES": stats.get("sources", 0),
        "STAT_RAW": stats.get("raw", 0),
        "STAT_ITEMS": stats.get("items", 0),
        "STAT_CLUSTERS": stats.get("clusters", 0),
        "STAT_DEDUPE": stats.get("dedupe_rate", "—"),
        "modules": modules,
        "cloud": [{"cloud_tag": esc(t)} for t in cloud],
        "issues": [
            {
                "issue_date": it["date"],
                "issue_weekday": it["weekday"],
                "issue_headline": esc(it["headline"]),
                "issue_deck": esc(it["deck"]),
                "issue_items": it["items"],
                "issue_selected": "selected" if it["date"] == day["date"] else "",
            }
            for it in issues
        ],
    }


def build_archive_context(issues, base):
    months = sorted({it["date"][:7] for it in issues}, reverse=True)
    month_options = "".join(
        '<option value="%s">%s 年 %d 月</option>' % (m, m[:4], int(m[5:7])) for m in months
    )

    cloud = []
    for it in issues:
        for tag in it.get("tags", []):
            if tag not in cloud:
                cloud.append(tag)

    rows = []
    for it in issues:
        hay = " ".join([it["date"], it.get("weekday", ""), it.get("headline", ""),
                        it.get("deck", ""), " ".join(it.get("tags", []))])
        rows.append({
            "row_url": it["url"],
            "row_date": it["date"],
            "row_weekday": it["weekday"],
            "row_issue": it["issue"],
            "row_headline": esc(it["headline"]),
            "row_deck": esc(it["deck"]),
            "row_items": it["items"],
            "row_sources": it["sources"],
            "row_month": it["date"][:7],
            "row_tags": "|".join(it.get("tags", [])),
            "row_hay": esc(hay),
        })

    return {
        "BASE": base,
        "TOTAL": len(issues),
        "UPDATED": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "MONTH_OPTIONS": month_options,
        "cloud": [{"cloud_tag": esc(t)} for t in cloud],
        "rows": rows,
        "issues": [
            {
                "issue_date": it["date"],
                "issue_weekday": it["weekday"],
                "issue_headline": esc(it["headline"]),
                "issue_deck": esc(it["deck"]),
                "issue_items": it["items"],
                "issue_selected": "",
            }
            for it in issues
        ],
    }


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="AI 日报静态站点生成")
    parser.add_argument("--latest", action="store_true", help="只渲染最新一期")
    parser.add_argument("--date", help="只渲染指定日期（YYYY-MM-DD）")
    args = parser.parse_args()

    day_files = sorted(
        f for f in os.listdir(DATA_DIR)
        if re.match(r"^\d{4}-\d{2}-\d{2}\.json$", f)
    )
    if not day_files:
        raise SystemExit("data/ 下没有日报 JSON，先跑 scripts/run_pipeline.py")

    issues, days = [], {}
    for name in day_files:
        day = read_json(os.path.join(DATA_DIR, name))
        days[day["date"]] = day
        issues.append(collect_issue_meta(day))
    issues.sort(key=lambda x: x["date"], reverse=True)

    # 索引同步：把历期元数据写回 data/index.json
    index_payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M CST"),
        "latest": issues[0]["date"],
        "issues": issues,
    }
    write_text(
        os.path.join(DATA_DIR, "index.json"),
        json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n",
    )

    # 资源落地
    os.makedirs(ASSET_DIR, exist_ok=True)
    write_text(os.path.join(ASSET_DIR, "style.css"),
               open(os.path.join(TPL_DIR, "partials.css"), encoding="utf-8").read())
    write_text(os.path.join(ASSET_DIR, "app.js"),
               open(os.path.join(TPL_DIR, "partials.js"), encoding="utf-8").read())

    daily_tpl = open(os.path.join(TPL_DIR, "daily.html"), encoding="utf-8").read()
    archive_tpl = open(os.path.join(TPL_DIR, "archive.html"), encoding="utf-8").read()

    if args.date:
        targets = [args.date]
    elif args.latest:
        targets = [issues[0]["date"]]
    else:
        targets = [it["date"] for it in issues]

    for date in targets:
        ctx = build_issue_context(days[date], issues, base="../")
        write_text(os.path.join(ARCHIVE_DIR, "%s.html" % date), render(daily_tpl, ctx))
        print("  ✓ archive/%s.html" % date)

    latest = issues[0]["date"]
    ctx = build_issue_context(days[latest], issues, base="")
    write_text(os.path.join(ROOT, "index.html"), render(daily_tpl, ctx))
    print("  ✓ index.html（最新一期 %s）" % latest)

    write_text(os.path.join(ROOT, "archive.html"),
               render(archive_tpl, build_archive_context(issues, base="")))
    print("  ✓ archive.html（共 %d 期）" % len(issues))


if __name__ == "__main__":
    main()
