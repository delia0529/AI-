"""
清洗去重层 —— 流水线第 1 段尾部：07:00 - 07:30

同一条新闻常被 Techmeme / Reuters / WSJ / CNBC 等多源转载。本脚本把标题向量化后做
贪心聚类，把每个簇折叠成一条「代表报道 + 全部来源」。

向量来源（按优先级）：
  1. OpenAI 兼容接口的 Embedding（配置 llm.embedding_model，需 OPENAI_API_KEY）
  2. 退化为字符 n-gram TF-IDF 余弦相似度（零依赖，结果略糙但可跑通）

输出： data/clean/<date>.json

用法：
  python3 scripts/dedupe.py --date 2026-09-17
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(ROOT, "data", "clean")
STOP = re.compile(r"[^\w一-鿿]+")


def tokenize(text):
    text = (text or "").lower()
    words = [w for w in STOP.split(text) if w]
    grams = []
    for w in words:
        if re.match(r"^[一-鿿]", w):
            grams += [w[i:i + 2] for i in range(max(1, len(w) - 1))]
        else:
            grams.append(w)
            grams += [w[i:i + 4] for i in range(max(1, len(w) - 3))]
    return grams or ["<empty>"]


def tfidf_vectors(texts):
    docs = [Counter(tokenize(t)) for t in texts]
    df = Counter()
    for d in docs:
        for term in d:
            df[term] += 1
    n = len(docs)
    vecs = []
    for d in docs:
        vec = {}
        for term, tf in d.items():
            idf = math.log((n + 1) / (df[term] + 0.5)) + 1
            vec[term] = (1 + math.log(tf)) * idf
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vecs.append({k: v / norm for k, v in vec.items()})
    return vecs


def embed_remote(texts, base_url, model, api_key):
    import urllib.request

    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/embeddings",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [row["embedding"] for row in data["data"]]


def cosine(a, b):
    if isinstance(a, dict):
        keys = set(a) & set(b)
        return sum(a[k] * b[k] for k in keys)
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def centroid(vectors):
    if not vectors:
        return []
    if isinstance(vectors[0], dict):
        merged = Counter()
        for v in vectors:
            merged.update(v)
        total = sum(merged.values()) or 1
        return {k: v / total for k, v in merged.items()}
    dim = len(vectors[0])
    out = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += x
    return [x / len(vectors) for x in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = ap.parse_args()

    config = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    dedupe_cfg = config.get("dedupe", {})
    raw_path = os.path.join(ROOT, "data", "raw", "%s.json" % args.date)
    if not os.path.exists(raw_path):
        raise SystemExit("缺少 %s，先跑 scripts/fetch_sources.py" % os.path.relpath(raw_path, ROOT))

    raw = json.load(open(raw_path, encoding="utf-8"))
    items = raw["items"]
    texts = ["%s %s" % (it["title"], it.get("summary", "")[:200]) for it in items]

    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        llm = config["llm"]
        vectors = embed_remote(texts, llm["base_url"], llm["embedding_model"], api_key)
        method = "embedding:%s" % llm["embedding_model"]
        threshold = dedupe_cfg.get("similarity_threshold", 0.86)
    else:
        vectors = tfidf_vectors(texts)
        method = "tfidf-fallback"
        # 标题改写会让不同源的 n-gram 重合度偏低，TF-IDF 兜底时用更宽松的阈值
        threshold = dedupe_cfg.get("tfidf_threshold", 0.52)
        print("[dedupe] 未检测到 OPENAI_API_KEY，使用本地 TF-IDF 兜底（阈值 %s）" % threshold)

    # 贪心聚类：权重高的条目优先成为簇心
    order = sorted(range(len(items)), key=lambda i: -items[i].get("weight", 1.0))
    clusters = []
    for i in order:
        best, best_sim = None, 0.0
        for c in clusters:
            sim = cosine(vectors[i], c["_centroid"])
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= threshold:
            best["members"].append(items[i])
            best["_vecs"].append(vectors[i])
            best["_centroid"] = centroid(best["_vecs"])
        else:
            clusters.append({"members": [items[i]], "_vecs": [vectors[i]],
                             "_centroid": vectors[i]})

    result = []
    for c in clusters:
        members = sorted(c["members"], key=lambda m: -(m.get("weight", 1.0) * 100 + m.get("points", 0)))
        lead = members[0]
        result.append({
            "headline": lead["title"],
            "url": lead["url"],
            "summary": lead.get("summary", ""),
            "score": round(lead.get("weight", 1.0) * 100 + lead.get("points", 0), 1),
            "sources": [{"name": m["source"], "url": m["url"], "title": m["title"]} for m in members],
            "duplicate_count": len(members),
        })
    result.sort(key=lambda x: -x["score"])

    os.makedirs(CLEAN_DIR, exist_ok=True)
    out = os.path.join(CLEAN_DIR, "%s.json" % args.date)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"date": args.date, "method": method, "threshold": threshold,
                   "raw_count": len(items), "clusters": result}, fh, ensure_ascii=False, indent=2)

    raw_n, kept_n = len(items), len(result)
    rate = "%.0f%%" % ((raw_n - kept_n) / raw_n * 100) if raw_n else "0%"
    print("[dedupe] %d 条 → %d 个聚类（多源重复率 %s，方法 %s）→ %s"
          % (raw_n, kept_n, rate, method, os.path.relpath(out, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
