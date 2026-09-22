"""
流水线编排 —— 一键跑完四个阶段

  06:00-07:30  fetch_sources.py  多源抓取 → data/raw/<date>.json
  07:00-07:30  dedupe.py         Embedding 聚类去重 → data/clean/<date>.json
  07:30-08:15  summarize.py      LLM 结构化提炼 → data/<date>.json
  08:15-08:45  build_site.py     SSG 渲染 → index.html / archive.html / archive/<date>.html
  09:00        notify.py         Webhook 推送 + git commit/push

用法：
  python3 scripts/run_pipeline.py                    # 跑完整条链路
  python3 scripts/run_pipeline.py --from-stage render
  python3 scripts/run_pipeline.py --skip-push --push-git
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
STAGES = ["fetch", "dedupe", "summarize", "render", "push"]


def run(cmd, cwd=ROOT):
    print("\n$ %s" % " ".join(cmd))
    started = time.time()
    proc = subprocess.run(cmd, cwd=cwd)
    if proc.returncode != 0:
        raise SystemExit("[pipeline] 阶段失败：%s（exit %s）" % (cmd[1], proc.returncode))
    print("  … 用时 %.1fs" % (time.time() - started))


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--from-stage", choices=STAGES, default="fetch")
    ap.add_argument("--skip-push", action="store_true", help="跳过 Webhook 推送")
    ap.add_argument("--push-git", action="store_true", help="渲染后自动 commit 并 push")
    args = ap.parse_args()

    start = STAGES.index(args.from_stage)
    plan = STAGES[start:]
    print("[pipeline] %s · 执行阶段：%s" % (args.date, " → ".join(plan)))

    if "fetch" in plan:
        run([sys.executable, os.path.join(SCRIPTS, "fetch_sources.py"), "--date", args.date, "--hours", str(args.hours)])
    if "dedupe" in plan:
        run([sys.executable, os.path.join(SCRIPTS, "dedupe.py"), "--date", args.date])
    if "summarize" in plan:
        run([sys.executable, os.path.join(SCRIPTS, "summarize.py"), "--date", args.date])
    if "render" in plan:
        run([sys.executable, os.path.join(SCRIPTS, "build_site.py"), "--latest"])
    if "push" in plan and not args.skip_push:
        run([sys.executable, os.path.join(SCRIPTS, "notify.py"), "--date", args.date])

    if args.push_git:
        git("add", "-A")
        msg = "chore(digest): %s 日报" % args.date
        res = git("commit", "-m", msg)
        print(res.stdout.strip() or res.stderr.strip())
        res = git("push")
        print(res.stdout.strip() or res.stderr.strip())

    print("\n[pipeline] 完成 → %s" % os.path.join(ROOT, "index.html"))


if __name__ == "__main__":
    main()
