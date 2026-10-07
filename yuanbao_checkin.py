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
  5. 使用P图能力 x3（从"去P图"入口; 相册选图后需要人工确认生成参数,
     脚本自动选图并截屏留档, 如 UI 有变化请人工补点）
  6. 参与体验优化计划（打开活动页留档）

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
  monitor/status.json  —— 供 Web 监控页读取
  logs/                —— 每步截屏留档
"""

import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

# ---------------- 配置 ----------------

DEVICE = "192.168.31.7:41681"          # adb 设备序列号（WiFi ADB）
APP_PKG = "com.tencent.hunyuan.app.chat"
BASE = Path(__file__).resolve().parent
LOG_DIR = BASE / "logs"
MONITOR_DIR = BASE / "docs"   # GitHub Pages 部署目录（Settings→Pages→/docs）
ASSET_DIR = BASE / "assets"

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
    "camera_gallery":   (220, 2090),   # 拍题/相机页左下角相册缩略图
    "picker_first":     (138, 366),    # 相册选择器第一个缩略图
    "crop_confirm":     (540, 2192),   # 拍题裁剪页"确认"
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
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
                   capture_output=True)
    shell(f"rm -f {remote}")
    return local


def scroll_down(times=2):
    for _ in range(times):
        swipe(540, 1700, 540, 700)
        time.sleep(1.2)


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


def push_question_images():
    """把 assets 下的题目图推送到相册并触发媒体扫描。"""
    pushed = 0
    for name in QUESTION_IMAGES:
        src = ASSET_DIR / name
        if not src.exists():
            log(f"缺少题目图 {src}, 跳过推送")
            continue
        dst = f"/sdcard/Pictures/{name}"
        subprocess.run(["adb", "-s", DEVICE, "push", str(src), dst],
                       capture_output=True)
        shell(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
              f"-d file://{dst}", timeout=15)
        pushed += 1
    log(f"题目图推送 {pushed}/{len(QUESTION_IMAGES)}")
    return pushed


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
    pushed = push_question_images()
    if pushed == 0:
        log("无题目图可用, 拍题任务跳过")
        return
    for i in range(1, 4):
        goto_welfare()
        tap(*COORDS["task_photo"])
        time.sleep(3.5)                    # 相机页
        tap(*COORDS["camera_gallery"])
        time.sleep(3)                      # 相册选择器
        tap(*COORDS["picker_first"])       # 最新推送的题目图在最前
        time.sleep(2.5)                    # 裁剪页
        tap(*COORDS["crop_confirm"])
        time.sleep(10)                     # 生成开始
        screenshot(f"photo_round{i}")
        log(f"拍题 第{i}次已提交")


def task_pimage():
    """P图: 打开入口 → 相册选图。选图后的模板/生成按钮因版本而异,
    脚本截屏留档, 剩余步骤参考 README 人工补点或按日志校准坐标。"""
    for i in range(1, 4):
        goto_welfare()
        tap(*COORDS["task_pimage"])
        time.sleep(3.5)
        tap(*COORDS["camera_gallery"])
        time.sleep(3)
        tap(*COORDS["picker_first"])
        time.sleep(3)
        screenshot(f"pimage_round{i}")
        log(f"P图 第{i}次: 已选图, 请按日志截屏核对生成是否完成")


def task_join():
    goto_welfare()
    tap(*COORDS["task_join"])
    time.sleep(3)
    screenshot("join_page")
    keyevent(4)
    log("体验优化计划: 活动页已打开并留档（如需填表请人工完成）")


TASKS = {
    "checkin": task_checkin,
    "ask": task_ask,
    "write": task_write,
    "photo": task_photo,
    "pimage": task_pimage,
    "join": task_join,
}


def write_status(results):
    MONITOR_DIR.mkdir(exist_ok=True)
    status = {
        "app": "yuanbao-checkin",
        "device": DEVICE,
        "last_run": datetime.datetime.now().isoformat(timespec="seconds"),
        "tasks": results,
        "log": RUN_LOG[-60:],
    }
    (MONITOR_DIR / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log("status.json 已写入 monitor/")


def main():
    global DEVICE
    ap = argparse.ArgumentParser(description="元宝福利中心每日任务自动化")
    ap.add_argument("--device", default=DEVICE)
    ap.add_argument("--only", nargs="*", default=list(TASKS),
                    choices=list(TASKS))
    args = ap.parse_args()
    DEVICE = args.device

    results = {}
    log(f"开始执行, 设备 {DEVICE}, 任务 {args.only}")
    grant_permissions()

    try:
        for name in args.only:
            fn = TASKS[name]
            try:
                fn()
                results[name] = "done"
            except Exception as e:  # 单任务失败不影响其余
                results[name] = f"error: {e}"
                log(f"任务 {name} 异常: {e}")
                screenshot(f"error_{name}")
    finally:
        write_status(results)

    log("全部结束")


if __name__ == "__main__":
    main()
