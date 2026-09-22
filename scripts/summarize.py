"""
结构化提炼层 —— 流水线第 2 段：07:30 - 08:15

调用大模型（OpenAI 兼容接口）把去重后的聚类提炼成规范 JSON：
  { 标题, 分类, 核心事实, 深度洞察, 关联标的/企业, 引用来源 }

产出 data/<date>.json，直接作为 SSG 的输入。没有配置 API Key 时不会编造内容，直接报错退出。

用法：
  python3 scripts/summarize.py --date 2026-09-17
  python3 scripts/summarize.py --date 2026-09-17 --print-prompt   # 只看 Prompt，不请求
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(ROOT, "data", "clean")
DATA_DIR = os.path.join(ROOT, "data")

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
PRIORITY = {"high", "mid", "low"}

SYSTEM_PROMPT = """你是一位服务于专业投资与研究机构的 AI 产业首席分析师。
请基于给定的候选新闻聚类，产出一期「AI 趋势日报」。

硬性要求：
1. 只使用候选素材中出现的事实，禁止编造任何数字、公司动作或引述。
2. 每条「深度洞察」必须回答「所以呢」——对竞争格局、成本结构、监管或资本开支的影响，而非复述事实。
3. 语言为简体中文，克制、具体，避免口号与形容词堆砌。
4. 引用来源必须来自候选素材的 sources 字段，最多保留 4 条。
5. 只输出 JSON，不要任何解释、Markdown 代码块或多余文字。
"""

USER_TEMPLATE = """日期：{date}
候选聚类（已去重，共 {n} 个）：
{candidates}

可选模块：
{modules}

可选标签（只能用这些，每条 1-3 个）：
{tags}

输出 JSON 结构（严格一致）：
{{
  "headline": "不超过 20 字的当日主标题，要有判断，不要写成导航词",
  "deck": "80-140 字的当日综述，把所有重要线索串成一段",
  "items": [
    {{
      "module_id": "上面可选模块之一",
      "title": "不超过 30 字的事实性标题",
      "category": "细分领域，如『AI 安全 / 政策』",
      "priority": "high | mid | low",
      "facts": "80-180 字，只写核心事实：谁、做了什么、关键数字与时间",
      "insight": "60-140 字，写这条为什么重要、对谁有利空/利好",
      "entities": ["关联公司或标的，2-5 个"],
      "tags": ["#标签"],
      "sources": [{{"name": "来源名", "url": "来源链接"}}],
      "images": [{{"url": "图片直链", "caption": "图注", "credit": "图源站点", "link": "原页面"}}]
    }}
  ]
}}

配图规则（仅模块 05 需要，其他模块留空数组）：
1. 只允许厂商官网、官方博客或第三方报道中的**真实产品截图 / 官方视觉图**；
2. **严禁使用任何 AI 生成的图片**，也不要臆造图片链接；
3. 无法确定直链时，就把 images 留空数组，并在 sources 里给出官方页面链接。

条数要求：{max_items} 条以内，宁缺毋滥；每个模块至少 1 条，最多 6 条。"""


def build_prompt(date, clusters, config):
    modules = "\n".join("- %s（%s）：%s" % (m["id"], m["name"], m.get("hint", "")) for m in config["modules"])
    candidates = []
    for i, c in enumerate(clusters, 1):
        srcs = "；".join("%s(%s)" % (s["name"], s["url"]) for s in c["sources"][:5])
        candidates.append(
            "[%02d] 分数 %s｜重复源 %d 个\n标题：%s\n摘要：%s\n来源：%s"
            % (i, c["score"], c["duplicate_count"], c["headline"], c["summary"][:300], srcs)
        )
    return USER_TEMPLATE.format(
        date=date,
        n=len(clusters),
        candidates="\n".join(candidates),
        modules=modules,
        tags="、".join(config["tags"]),
        max_items=config["llm"].get("max_items", 24),
    )


def call_llm(system_prompt, user_prompt, config):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("未设置 OPENAI_API_KEY，无法调用大模型；本脚本不会编造日报内容。")
    llm = config["llm"]
    payload = json.dumps({
        "model": llm["model"],
        "temperature": llm.get("temperature", 0.2),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        llm["base_url"].rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def extract_json(text):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型输出中没有找到 JSON 对象")
    return json.loads(text[start:end + 1])


def validate(payload, config):
    if "headline" not in payload or "items" not in payload:
        raise ValueError("JSON 缺少 headline / items 字段")
    module_ids = {m["id"] for m in config["modules"]}
    tag_set = set(config["tags"])
    clean = []
    for item in payload["items"]:
        if item.get("module_id") not in module_ids:
            continue
        item["priority"] = item.get("priority", "mid")
        if item["priority"] not in PRIORITY:
            item["priority"] = "mid"
        item["tags"] = [t for t in item.get("tags", []) if t in tag_set][:3]
        if not item["tags"]:
            continue
        item["entities"] = item.get("entities", [])[:5]
        item["sources"] = [s for s in item.get("sources", []) if s.get("url")][:4]
        # 配图最多 3 张，且必须是真实链接
        item["images"] = [im for im in item.get("images", []) if im.get("url", "").startswith("http")][:3]
        if not item["sources"]:
            continue
        clean.append(item)
    payload["items"] = clean
    if not clean:
        raise ValueError("没有通过校验的条目")
    return payload


def assemble(date, payload, clusters, config):
    by_module = {}
    for m in config["modules"]:
        by_module[m["id"]] = {
            "id": m["id"],
            "index": m["index"],
            "name": m["name"],
            "en": m["en"],
            "note": m.get("note", ""),
            "watchlist": m.get("watchlist", []),
            "items": [],
        }
    for i, item in enumerate(payload["items"], 1):
        mod = by_module[item["module_id"]]
        item["id"] = "%s-%d" % (mod["id"], len(mod["items"]) + 1)
        mod["items"].append(item)

    modules = [m for m in by_module.values() if m["items"]]
    modules.sort(key=lambda m: m["index"])
    total_items = sum(len(m["items"]) for m in modules)

    prev = datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)
    stats = {
        "sources": len({s["name"] for c in clusters for s in c["sources"]}),
        "raw": clusters[0]["duplicate_count"] and sum(c["duplicate_count"] for c in clusters) or len(clusters),
        "items": total_items,
        "clusters": len(clusters),
        "dedupe_rate": "%.0f%%" % ((1 - len(clusters) / max(1, sum(c["duplicate_count"] for c in clusters))) * 100),
    }
    return {
        "date": date,
        "issue": payload.get("issue", "No.%s" % date.replace("-", "")),
        "weekday": WEEKDAY_CN[datetime.strptime(date, "%Y-%m-%d").weekday()],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M CST"),
        "window": "%s 09:00 → %s 09:00 CST" % (prev.strftime("%Y-%m-%d"), date),
        "headline": payload["headline"],
        "deck": payload["deck"],
        "stats": stats,
        "modules": modules,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--print-prompt", action="store_true")
    args = ap.parse_args()

    config = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    clean_path = os.path.join(CLEAN_DIR, "%s.json" % args.date)
    if not os.path.exists(clean_path):
        raise SystemExit("缺少 %s，先跑 scripts/dedupe.py" % os.path.relpath(clean_path, ROOT))
    clusters = json.load(open(clean_path, encoding="utf-8"))["clusters"]

    user_prompt = build_prompt(args.date, clusters, config)
    if args.print_prompt:
        print(SYSTEM_PROMPT + "\n\n" + user_prompt)
        return 0

    raw_out = call_llm(SYSTEM_PROMPT, user_prompt, config)
    payload = validate(extract_json(raw_out), config)
    day = assemble(args.date, payload, clusters, config)

    out = os.path.join(DATA_DIR, "%s.json" % args.date)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(day, fh, ensure_ascii=False, indent=2)
    print("[summarize] %d 个模块 / %d 条 → %s" % (len(day["modules"]), day["stats"]["items"], os.path.relpath(out, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
