"""
定时发布与分发 —— 流水线第 4 段：09:00

把当日「头条精粹 + 静态网页直达链接」推送到飞书 / 企业微信 / 邮件。
Webhook 地址一律从环境变量读取，禁止硬编码进仓库。

用法：
  python3 scripts/notify.py --date 2026-09-17
  python3 scripts/notify.py --date 2026-09-17 --dry-run
"""

import argparse
import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_day(date):
    path = os.path.join(ROOT, "data", "%s.json" % date)
    if not os.path.exists(path):
        raise SystemExit("缺少 %s" % path)
    return json.load(open(path, encoding="utf-8"))


def build_digest(day, base_url, top_n=3):
    items = []
    for m in day.get("modules", []):
        for it in m.get("items", []):
            items.append((m, it))
    items.sort(key=lambda pair: {"high": 0, "mid": 1, "low": 2}.get(pair[1].get("priority", "mid"), 1))
    top = items[:top_n]

    lines = ["**%s · AI 趋势日报 %s**" % (day["date"], day.get("issue", "")),
             "> %s" % day.get("headline", ""),
             ""]
    for i, (m, it) in enumerate(top, 1):
        src = it.get("sources", [{}])[0]
        lines.append("**%d. %s**" % (i, it["title"]))
        lines.append("%s" % it.get("facts", "")[:180])
        if src.get("url"):
            lines.append("来源：%s" % src["url"])
        lines.append("")
    lines.append("🔗 完整日报：%s/archive/%s.html" % (base_url.rstrip("/"), day["date"]))
    lines.append("🗂 历史归档：%s/archive.html" % base_url.rstrip("/"))
    return "\n".join(lines)


def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def push_feishu(webhook, text, title):
    return post_json(webhook, {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": text}}],
        },
    })


def push_wecom(webhook, text):
    return post_json(webhook, {"msgtype": "markdown", "markdown": {"content": text}})


def push_email(smtp_url, subject, text):
    """smtp_url 形如 smtp://user:pass@smtp.example.com:587"""
    from urllib.parse import urlparse, unquote

    u = urlparse(smtp_url)
    host, port = u.hostname, u.port or 587
    user, password = unquote(u.username or ""), unquote(u.password or "")
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = user
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    return 250, "sent"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    day = load_day(args.date)
    base_url = config["site"]["base_url"]
    top_n = config.get("push", {}).get("top_n", 3)
    text = build_digest(day, base_url, top_n)
    title = "%s AI 趋势日报 · %s" % (day["date"], day.get("headline", ""))

    if args.dry_run:
        print(text)
        return 0

    sent = 0
    for env, fn in (
        (config["push"]["feishu_env"], lambda u: push_feishu(u, text, title)),
        (config["push"]["wecom_env"], lambda u: push_wecom(u, text)),
        (config["push"]["smtp_env"], lambda u: push_email(u, title, text)),
    ):
        url = os.environ.get(env)
        if not url:
            continue
        try:
            status, _ = fn(url)
            print("  ✓ %s 推送成功（%s）" % (env, status))
            sent += 1
        except Exception as exc:
            print("  ! %s 推送失败：%s" % (env, exc))
    if not sent:
        print("[notify] 未配置任何 Webhook 环境变量，跳过推送（可用 --dry-run 预览内容）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
