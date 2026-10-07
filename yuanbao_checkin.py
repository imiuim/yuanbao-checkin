#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯元宝福利中心每日任务自动化（ADB 版）

适配设备: Redmi 22127RK46C (1080x2400, MIUI), 通过 WiFi ADB 连接。
其他分辨率设备需要重新标定 COORDS 中的坐标（用 adb shell getevent / 开发者选项
"指针位置" 逐个核对）。

覆盖任务:
  1. 元宝能力站打卡（第1天卡片）
  2. 趣问元宝得积分 x3（从福利页"去提问"入口进入才计数）
  3. 使用写作能力 x3（从"去写作"入口进入才计数）
  4. 使用拍题能力 x3（从"去拍题"入口进入才计数, 相册选预置题目图）
  5. 使用P图能力 x3（"去P图"入口 → 相册选图 → 智能P图页发送生成）
  6. 参与体验优化计划（打开设置页留档; 隐私开关需用户手动开一次）

重要经验（踩坑记录）:
  - 福利页是 H5, uiautomator 拿不到内部控件, 只能坐标点击。
  - 任务计数必须从福利中心页面的"去XX"按钮进入, 从聊天工具栏进入同一功能不计入。
  - 聊天里 AI 生成完成与否不影响计数, 生成开始后即可返回。
  - 打卡点击后 UI 不一定刷新, 重进福利页才能看到"已打卡"。

用法:
  python yuanbao_checkin.py                    # 全部任务
  python yuanbao_checkin.py --only checkin ask write  # 只跑部分任务
  python yuanbao_checkin.py --device 192.168.31.7:41681
输出:
  docs/status.json     —— 供 Web 监控页读取（运行后自动 commit+push）
  docs/points.png      —— 福利页积分余额截图（监控页展示）
  logs/                —— 每步截屏留档
"""

import argparse
import configparser
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

# ---------------- 配置 ----------------

# 经 pythonw/隐藏 VBS 拉起时, adb/git 等控制台子进程必须显式隐藏, 否则闪黑框
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

DEVICE = "192.168.31.7:41681"          # adb 设备序列号（WiFi ADB）
APP_PKG = "com.tencent.hunyuan.app.chat"
BASE = Path(__file__).resolve().parent
LOG_DIR = BASE / "logs"
MONITOR_DIR = BASE / "docs"   # GitHub Pages 部署目录（Settings→Pages→/docs）
ASSET_DIR = BASE / "assets"
LOCK = BASE / ".run.lock"
GIT_IDENTITY = ["-c", "user.name=刘演",
                "-c", "user.email=79697331+ovlineen@users.noreply.github.com"]

# 可选 config.ini:
#   [account] name = 用户a797
_cfg = configparser.ConfigParser()
_cfg.read(BASE / "config.ini", encoding="utf-8")
ACCOUNT = _cfg.get("account", "name", fallback="用户a797")

# 坐标表（1080x2400）
COORDS = {
    "hamburger":        (102, 180),    # 主界面左上角菜单
    "welfare_entry":    (235, 538),    # 侧边栏"福利中心"
    "checkin_day1":     (150, 750),    # 能力站"第1天"卡片
    "ask_btn_1":        (274, 1722),   # 趣问元宝 去提问 #1
    "ask_btn_2":        (596, 1722),   # 去提问 #2
    "ask_btn_3":        (912, 1722),   # 去提问 #3
    "chat_jump_bottom": (540, 1872),   # 回答页 ↓ 跳到底部
    "back_to_welfare":  (270, 1742),   # "返回福利中心" 胶囊按钮
    "task_join":        (912, 696),    # 每日任务: 去参与
    "task_write":       (912, 910),    # 去写作
    "task_photo":       (912, 1123),   # 去拍题
    "task_pimage":      (912, 1336),   # 去P图
    "camera_gallery":   (220, 2090),   # 拍题相机页左下角相册缩略图
    "picker_first":     (138, 366),    # 相册选择器第一个缩略图
    "picker_first_r2":  (396, 540),    # P图选择器第二格（第一格是"相机"块）
    "crop_confirm":     (540, 2192),   # 拍题裁剪页"确认"
    "pimage_send":      (952, 1298),   # 智能P图页发送按钮
    "write_input":      (444, 2230),   # AI写作 输入框
    "write_send":       (960, 1280),   # AI写作 发送(键盘弹起时)
}

WRITE_TOPICS = [
    "the benefits of morning exercise",
    "how to stay focused while working from home",
    "simple habits for better sleep quality",
]

QUESTION_IMAGES = ["q1.png", "q2.png", "q3.png"]  # assets/ 下的题目图, 推到相册用

# ---------------- ADB 基础 ----------------


def adb(*args, timeout=30):
    cmd = ["adb", "-s", DEVICE, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       creationflags=CREATE_NO_WINDOW)
    return r.stdout.strip()


def shell(cmd, timeout=30):
    return adb("shell", cmd, timeout=timeout)


def tap(x, y):
    shell(f"input tap {x} {y}")


def swipe(x1, y1, x2, y2, ms=400):
    shell(f"input swipe {x1} {y1} {x2} {y2} {ms}")


def keyevent(code):
    shell(f"input keyevent {code}")


def screenshot(name):
    LOG_DIR.mkdir(exist_ok=True)
    remote = "/sdcard/yb_auto_shot.png"
    shell(f"screencap -p {remote}")
    local = LOG_DIR / f"{name}.png"
    subprocess.run(["adb", "-s", DEVICE, "pull", remote, str(local)],
                   capture_output=True, creationflags=CREATE_NO_WINDOW)
    shell(f"rm -f {remote}")
    return local


def scroll_down(times=2):
    for _ in range(times):
        swipe(540, 1700, 540, 700)
        time.sleep(1.2)


def ensure_connected():
    """WiFi ADB 重连; 失败则尝试 mDNS 发现新的无线调试端口。返回是否可用。"""
    out = adb("devices", timeout=15)
    if DEVICE in out and "\tdevice" in out:
        return True
    adb("connect", DEVICE, timeout=15)
    out = adb("devices", timeout=15)
    if DEVICE in out and "\tdevice" in out:
        return True
    # 尝试 mDNS 自动发现 (需手机"无线调试"开启): _adb-tls-connect._tcp
    try:
        services = adb("mdns", "services", timeout=15)
        for line in services.splitlines():
            if "_adb-tls-connect" in line:
                cand = line.split()[-2] if len(line.split()) >= 2 else None
                if cand and ":" in cand:
                    adb("connect", cand, timeout=15)
                    out = adb("devices", timeout=15)
                    if cand in out and "\tdevice" in out:
                        globals()["DEVICE"] = cand
                        return True
    except Exception:
        pass
    return False


def wake_device():
    """点亮屏幕并上滑解锁（无密码锁屏时有效）。"""
    shell("input keyevent 224")            # KEYCODE_WAKEUP
    time.sleep(1.5)
    swipe(540, 2000, 540, 900, 300)        # 上滑
    time.sleep(1.5)


# ---------------- 流程 ----------------

RUN_LOG = []


def log(msg):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    RUN_LOG.append(line)


def goto_welfare():
    """从任意界面回到福利中心任务列表（干净复位）。"""
    keyevent(3)                 # HOME, 避免在错误页面上继续点
    time.sleep(1)
    adb("shell", f"monkey -p {APP_PKG} -c android.intent.category.LAUNCHER 1",
        timeout=30)
    time.sleep(2.5)
    tap(*COORDS["hamburger"])
    time.sleep(1.5)
    tap(*COORDS["welfare_entry"])
    time.sleep(2.5)
    scroll_down(2)


def grant_permissions():
    """预授权, 避免运行中出现系统权限弹窗。"""
    for perm in ("android.permission.CAMERA",
                 "android.permission.READ_MEDIA_IMAGES",
                 "android.permission.READ_EXTERNAL_STORAGE"):
        shell(f"pm grant {APP_PKG} {perm}", timeout=15)


# ---- 各任务实现 ----

def task_checkin():
    tap(*COORDS["checkin_day1"])
    time.sleep(2)
    screenshot("checkin_after_tap")
    log("打卡: 已点击第1天卡片（若今日已打卡则无副作用）")


def task_ask():
    for i, btn in enumerate(("ask_btn_1", "ask_btn_2", "ask_btn_3"), 1):
        goto_welfare()
        tap(*COORDS[btn])
        time.sleep(6)                      # 问题发出并开始生成
        tap(*COORDS["chat_jump_bottom"])   # ↓ 到底
        time.sleep(1.5)
        tap(*COORDS["back_to_welfare"])    # 返回福利中心
        time.sleep(2)
        screenshot(f"ask_round{i}")
        log(f"趣问元宝 第{i}问已提交")


def task_write():
    for i, topic in enumerate(WRITE_TOPICS, 1):
        goto_welfare()
        tap(*COORDS["task_write"])
        time.sleep(2.5)                    # AI写作面板
        tap(*COORDS["write_input"])
        time.sleep(1.2)
        shell(f"input text {topic.replace(' ', '%s')}")
        time.sleep(0.8)
        tap(*COORDS["write_send"])
        time.sleep(18)                     # 生成开始即计数
        keyevent(4)                        # 返回福利中心
        time.sleep(2)
        screenshot(f"write_round{i}")
        log(f"写作 第{i}篇已提交: {topic}")


def task_photo():
    """拍题: 每轮推送一张全新题目图(保证在相册选择器最前), 从"去拍题"入口进入。"""
    for i, name in enumerate(QUESTION_IMAGES, 1):
        src = ASSET_DIR / name
        if not src.exists():
            log(f"缺少题目图 {src}, 第{i}轮跳过")
            continue
        dst = f"/sdcard/Pictures/auto_{name}"
        subprocess.run(["adb", "-s", DEVICE, "push", str(src), dst],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
        shell(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
              f"-d file://{dst}", timeout=15)
        time.sleep(1)
        goto_welfare()
        tap(*COORDS["task_photo"])
        time.sleep(3.5)                    # 相机页
        tap(*COORDS["camera_gallery"])
        time.sleep(3)                      # 相册选择器
        tap(*COORDS["picker_first"])       # 最新推送的题目图在最前
        time.sleep(2.5)                    # 裁剪页
        tap(*COORDS["crop_confirm"])
        time.sleep(10)                     # 生成开始即计数
        screenshot(f"photo_round{i}")
        log(f"拍题 第{i}次已提交")


def task_pimage():
    """P图: "去P图"直接打开相册选择器(本地相册) → 选图 → 智能P图页点发送。
    选图坐标取第二格(第一格是"相机"块), 若相册缩略图布局变化需重新标定。"""
    for i in range(1, 4):
        goto_welfare()
        tap(*COORDS["task_pimage"])
        time.sleep(3.5)                    # 本地相册选择器
        tap(*COORDS["picker_first_r2"])
        time.sleep(3)                      # 智能P图编辑页, 图片1已挂上
        tap(*COORDS["pimage_send"])
        time.sleep(12)                     # 生成
        screenshot(f"pimage_round{i}")
        log(f"P图 第{i}次已提交")


def task_join():
    """体验优化计划: 仅打开设置页并留档。
    注意: 计数需要开启"体验优化计划"开关, 这涉及数据使用授权,
    由用户手动开启一次即可（之后每日无需再做）。脚本不代开隐私开关。"""
    goto_welfare()
    tap(*COORDS["task_join"])
    time.sleep(3)
    screenshot("join_page")
    keyevent(4)
    log("体验优化计划: 设置页已打开并留档（开关请用户手动确认）")


TASKS = {
    "checkin": task_checkin,
    "ask": task_ask,
    "write": task_write,
    "photo": task_photo,
    "pimage": task_pimage,
    "join": task_join,
}


def capture_points():
    """回福利页顶部, 截取积分余额条 -> docs/points.png（监控页展示）。"""
    goto_welfare()
    for _ in range(4):                     # 回到页面顶部
        swipe(540, 600, 540, 1900, 300)
        time.sleep(0.8)
    time.sleep(1.5)
    local = screenshot("points_full")
    try:
        from PIL import Image
        img = Image.open(local)
        # 积分余额条 "✦ NNNNN" 区域（1080x2400 实测）
        img.crop((40, 315, 430, 455)).save(
            MONITOR_DIR / "points.png", quality=88)
        log("积分余额截图已更新 docs/points.png")
    except Exception as e:
        log(f"积分截图裁剪失败(不影响任务): {e}")


def write_status(results):
    MONITOR_DIR.mkdir(exist_ok=True)
    # 当日累计: --only 部分运行时保留当天已完成的其余任务状态, 跨天重置
    path = MONITOR_DIR / "status.json"
    tasks = {}
    today = f"{datetime.datetime.now():%Y-%m-%d}"
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
        if prev.get("run_date") == today:
            tasks.update(prev.get("tasks", {}))
    except Exception:
        pass
    # 当日已 done 的任务不被重跑的 error/device_offline 降级（奖励当天已领）
    for k, v in results.items():
        if tasks.get(k) == "done" and v != "done":
            continue
        tasks[k] = v

    status = {
        "app": "yuanbao-checkin",
        "account": ACCOUNT,
        "device": DEVICE,
        "run_date": today,
        "last_run": datetime.datetime.now().isoformat(timespec="seconds"),
        "points_image": f"points.png?v={datetime.datetime.now():%Y%m%d%H%M%S}",
        "tasks": tasks,
        "log": RUN_LOG[-60:],
    }
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    log("status.json 已写入 docs/")


def push_status():
    """把 docs/（status+积分截图）提交并推送到 GitHub, 供线上监控页展示。"""
    try:
        subprocess.run(["git", "add", "-A", "docs/"], cwd=BASE, check=True,
                       timeout=30, capture_output=True,
                       creationflags=CREATE_NO_WINDOW)
        c = subprocess.run(["git", *GIT_IDENTITY, "commit", "-m",
                            f"run: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"],
                           cwd=BASE, capture_output=True, text=True, timeout=30,
                           creationflags=CREATE_NO_WINDOW)
        if c.returncode != 0 and "nothing to commit" not in c.stdout:
            log(f"git commit 异常: {c.stderr.strip()[:200]}")
        subprocess.run(["git", "-c", "http.proxy=", "-c", "https.proxy=",
                        "pull", "--rebase", "origin", "main"],
                       cwd=BASE, capture_output=True, timeout=60,
                       creationflags=CREATE_NO_WINDOW)
        p = subprocess.run(["git", "-c", "http.proxy=", "-c", "https.proxy=",
                            "push"], cwd=BASE, capture_output=True, timeout=90,
                           creationflags=CREATE_NO_WINDOW)
        log("git push " + ("成功" if p.returncode == 0
                           else f"失败: {p.stderr.decode(errors='ignore')[:200]}"))
    except Exception as e:
        log(f"推送状态失败(不影响任务): {e}")


def main():
    global DEVICE
    ap = argparse.ArgumentParser(description="元宝福利中心每日任务自动化")
    ap.add_argument("--device", default=DEVICE)
    ap.add_argument("--only", nargs="*", default=list(TASKS),
                    choices=list(TASKS))
    args = ap.parse_args()
    DEVICE = args.device

    if LOCK.exists():
        log("检测到 .run.lock, 已有任务在运行, 本次退出")
        return
    LOCK.write_text(str(time.time()))

    results = {}
    try:
        log(f"开始执行, 设备 {DEVICE}, 任务 {args.only}")
        if not ensure_connected():
            log("设备不可达: 请确认手机与电脑同一 WiFi、无线调试已开启;"
                "若端口变化请更新 --device 或依赖 mDNS 自动发现")
            write_status({k: "device_offline" for k in args.only})
            push_status()
            return
        wake_device()
        grant_permissions()

        for name in args.only:
            fn = TASKS[name]
            try:
                fn()
                results[name] = "done"
            except Exception as e:  # 单任务失败不影响其余
                results[name] = f"error: {e}"
                log(f"任务 {name} 异常: {e}")
                screenshot(f"error_{name}")

        capture_points()
    finally:
        write_status(results)
        push_status()
        LOCK.unlink(missing_ok=True)

    log("全部结束")


if __name__ == "__main__":
    main()
