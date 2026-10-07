#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
远程触发监听器（GitHub trigger 文件轮询模式）

原理: 电脑每分钟由计划任务调起本脚本(--once), 读取仓库 docs/trigger.json;
当 "run": true 时在本地执行 yuanbao_checkin.py, 完成后:
  1. 由主脚本自动 commit+push 最新的 docs/status.json、docs/points.png
  2. 本脚本把 trigger.json 回写为 run:false 并记录 last_completed/last_result

远程触发方式（手机浏览器即可）:
  打开 https://github.com/imiuim/yuanbao-checkin/edit/main/docs/trigger.json
  把 "run": false 改成 "run": true, 点 Commit changes, 60 秒内自动执行。

无需公网暴露电脑端口; 所有通信走 GitHub API（凭据来自 Windows 凭据管理器,
即平时 git push 所用的同一份）。

用法:
  python remote_listener.py --once        # 计划任务每分钟调用
  python remote_listener.py --once --dry-run   # 只读判断+回写, 不真跑任务
"""

import argparse
import base64
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = "imiuim/yuanbao-checkin"
BRANCH = "main"
TRIGGER_PATH = "docs/trigger.json"
LOCK = BASE / ".run.lock"
GH_USER = "imiuim"
TRIGGER_MAX_AGE_HOURS = 24   # 超过 24 小时前的触发请求视为过期, 忽略


def gh_token():
    """从 Windows 凭据管理器取 GitHub token（与 git push 同源）。"""
    env = {**os.environ, "GCM_INTERACTIVE": "Never",
           "GIT_TERMINAL_PROMPT": "0"}
    inp = f"protocol=https\nhost=github.com\nusername={GH_USER}\n\n"
    try:
        p = subprocess.run(["git", "credential", "fill"], input=inp,
                           capture_output=True, text=True, env=env, timeout=20)
        for line in p.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return None


def api(method, path, token, payload=None):
    """GitHub API 调用; ProxyHandler({}) 强制直连, 绕过本机可能失效的代理。"""
    url = f"https://api.github.com{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=20) as r:
        body = r.read()
    return json.loads(body) if body else {}


def read_trigger(token):
    d = api("GET", f"/repos/{REPO}/contents/{TRIGGER_PATH}?ref={BRANCH}",
            token)
    return json.loads(base64.b64decode(d["content"]).decode("utf-8")), d["sha"]


def write_trigger(token, obj, sha):
    api("PUT", f"/repos/{REPO}/contents/{TRIGGER_PATH}", token, {
        "message": f"trigger: {obj.get('run')} "
                   f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        "content": base64.b64encode(
            json.dumps(obj, ensure_ascii=False, indent=2)
            .encode("utf-8")).decode(),
        "sha": sha,
        "branch": BRANCH,
    })


def run_checkin(dry=False):
    """带锁执行打卡脚本, 返回结果描述。"""
    if LOCK.exists():
        age = time.time() - float(LOCK.read_text().strip() or 0)
        if age < 3600:
            return "already_running"
        LOCK.unlink(missing_ok=True)   # 残留超过 1 小时的锁视为异常
    if dry:
        return "dry_run_skipped"
    LOCK.write_text(str(time.time()))
    try:
        exe = sys.executable or "python"
        r = subprocess.run([exe, "yuanbao_checkin.py"], cwd=BASE,
                           capture_output=True, text=True, timeout=1800)
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        return f"exit={r.returncode} {tail[0][:120]}"
    finally:
        LOCK.unlink(missing_ok=True)


def once(dry=False):
    token = gh_token()
    if not token:
        print("no github token, skip", flush=True)
        return 1
    try:
        trig, sha = read_trigger(token)
    except Exception as e:
        print(f"read trigger failed: {e}", flush=True)
        return 1
    if not trig.get("run"):
        print("no pending trigger", flush=True)
        return 0

    requested_at = trig.get("requested_at")
    if requested_at:
        age_h = (datetime.datetime.now() -
                 datetime.datetime.fromisoformat(requested_at)).total_seconds() / 3600
        if age_h > TRIGGER_MAX_AGE_HOURS:
            print(f"trigger expired ({age_h:.1f}h), ignore", flush=True)
            write_trigger(token, {"run": False, "requested_at": requested_at,
                                  "last_result": "expired",
                                  "last_completed": None}, sha)
            return 0

    print(f"trigger received (at {requested_at}), running checkin...", flush=True)
    result = run_checkin(dry)
    print(f"checkin result: {result}", flush=True)

    try:
        trig2, sha2 = read_trigger(token)   # 期间文件可能被改动, 取最新 sha
        write_trigger(token, {
            "run": False,
            "requested_at": trig2.get("requested_at") or requested_at,
            "last_completed": datetime.datetime.now().isoformat(timespec="seconds"),
            "last_result": result,
        }, sha2)
        print("trigger.json reset", flush=True)
    except Exception as e:
        print(f"reset trigger failed: {e}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="检查一次后退出")
    ap.add_argument("--dry-run", action="store_true",
                    help="不真正执行打卡, 其余流程照走")
    args = ap.parse_args()
    sys.exit(once(dry=args.dry_run))


if __name__ == "__main__":
    main()
