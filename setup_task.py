#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
注册/更新 Windows 计划任务（当前用户, 无需管理员）:

  YuanbaoCheckinDaily    每天 00:00 触发 + 随机延迟 0~2 小时执行打卡
                         （错过后开机补跑; 不限制电池/接电状态）
  YuanbaoRemoteTrigger   每 1 分钟检查一次 docs/trigger.json, 响应远程触发

用法: python setup_task.py            # 注册/覆盖两个任务
      python setup_task.py --remove   # 删除两个任务
      python setup_task.py --query    # 查看状态
"""

import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

DAILY_TASK = "YuanbaoCheckinDaily"
TRIGGER_TASK = "YuanbaoRemoteTrigger"

# pythonw 绝对路径, 避免计划任务 PATH 解析问题
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
if not PYTHONW.exists():
    PYTHONW = Path(sys.executable)

# 每日任务起点明天 00:00（配合 RandomDelay 落在 0-2 点）;
# 监听任务起点今天 00:00, 注册后立即生效
START_DAILY, START_LOOP = "2026-10-08", "2026-10-07"

XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{desc}</Description>
  </RegistrationInfo>
  <Triggers>
    {trigger}
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>{limit}</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{cmd}</Command>
      <Arguments>{args}</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""

DAILY_TRIGGER = """<CalendarTrigger>
      <StartBoundary>{start}T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
      <RandomDelay>PT2H</RandomDelay>
    </CalendarTrigger>"""

LOOP_TRIGGER = """<TimeTrigger>
      <StartBoundary>{start}T00:00:00</StartBoundary>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <Enabled>true</Enabled>
    </TimeTrigger>"""


def schtasks(*args):
    r = subprocess.run(["schtasks", *args], capture_output=True,
                       encoding="gbk", errors="replace", timeout=30)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def write_xml(path, desc, trigger, limit, cmd, args_, workdir, start):
    trigger_xml = trigger.format(start=start)
    xml = XML_TEMPLATE.format(desc=desc, trigger=trigger_xml, limit=limit,
                              cmd=cmd, args=args_, workdir=workdir)
    # schtasks /XML 要求 UTF-16
    Path(path).write_text(xml, encoding="utf-16")
    return Path(path)


def register():
    vbs = BASE / "run_daily.vbs"

    xml_daily = write_xml(
        BASE / "task_daily.xml",
        "元宝福利中心每日打卡: 每天 00:00 + 随机 0~2 小时",
        DAILY_TRIGGER, "PT2H",
        "wscript.exe", f'"{vbs}"', str(BASE), START_DAILY)

    xml_loop = write_xml(
        BASE / "task_trigger.xml",
        "元宝远程触发监听: 每分钟检查 docs/trigger.json",
        LOOP_TRIGGER, "PT5M",
        str(PYTHONW), "remote_listener.py --once", str(BASE), START_LOOP)

    for xml, name in ((xml_daily, DAILY_TASK), (xml_loop, TRIGGER_TASK)):
        code, out = schtasks("/Create", "/F", "/TN", name, "/XML", str(xml))
        print(f"[{name}] {'registered' if code == 0 else 'FAILED'} -> {out.strip()}")
        xml.unlink(missing_ok=True)


def remove():
    for name in (DAILY_TASK, TRIGGER_TASK):
        code, out = schtasks("/Delete", "/F", "/TN", name)
        print(f"[{name}] {'removed' if code == 0 else out.strip()}")


def query():
    for name in (DAILY_TASK, TRIGGER_TASK):
        code, out = schtasks("/Query", "/TN", name, "/V", "/FO", "LIST")
        if code == 0:
            for line in out.splitlines():
                if any(k in line for k in ("任务名", "TaskName", "下次运行",
                                           "Next Run", "状态", "Status",
                                           "上次运行", "Last Run")):
                    print(line.strip())
        else:
            print(f"[{name}] not found")
        print("-" * 40)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--query", action="store_true")
    args = ap.parse_args()
    if args.remove:
        remove()
    elif args.query:
        query()
    else:
        register()
