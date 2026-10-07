# yuanbao-checkin

腾讯元宝（com.tencent.hunyuan.app.chat）福利中心每日任务自动化脚本 + Web 监控页。

通过 ADB 模拟点击完成元宝"福利中心"的日常积分任务，支持**每天 0-2 点随机自动执行**、
**GitHub 远程触发**，运行结果（任务状态 + 积分余额截图）自动推送到 GitHub Pages 监控页。

## 功能总览

| 能力 | 实现 |
|---|---|
| 每日自动打卡 | 计划任务每天 00:00 触发，系统级 RandomDelay 0~2h 随机执行 |
| 远程触发 | 监听器每分钟轮询仓库 `docs/trigger.json`，手机上改一个字段即可触发 |
| Web 监控页 | GitHub Pages 展示任务状态、账号、积分余额截图、运行日志 |
| 结果上报 | 每次运行后自动 commit + push `docs/`（status.json / points.png） |

## 任务覆盖

| 任务 | 积分 | 方式 |
|---|---|---|
| 元宝能力站打卡 | 8000 | 点击"第1天"卡片 |
| 趣问元宝 ×3 | 1500 | 福利页"去提问"入口逐个提问 |
| 使用写作能力 ×3 | 1500 | "去写作"入口，输入英文主题生成 |
| 使用拍题能力 ×3 | 1500 | "去拍题"入口，相册选预置题目图 |
| 使用P图能力 ×3 | 1500 | "去P图"入口 → 相册选图 → 智能P图页发送 |
| 参与体验优化计划 | 3000 | 打开设置页（隐私开关需用户手动开一次） |
| 邀2名新用户 | - | 需真实新用户，无法自动化，跳过 |

## 前提条件

- 电脑：`adb` 在 PATH；计划任务为"仅交互式"，运行时段**电脑需已登录且未休眠**。
- 手机：与电脑同一 WiFi，"无线调试"已开启并完成过一次配对连接；
  过夜建议插电、关闭锁屏密码（或无锁屏），否则脚本无法解锁进入。
- 元宝 App 保持登录状态。

## 使用

### 1. 手动运行

```bash
python yuanbao_checkin.py                       # 全部任务
python yuanbao_checkin.py --only checkin ask    # 只跑指定任务
python yuanbao_checkin.py --device <serial>     # 指定设备
```

运行期间不要操作手机。日志与每步截屏在 `logs/`。
脚本会自动: 唤醒并解锁屏幕 → WiFi ADB 重连（含 mDNS 自动发现新端口）→ 执行任务 →
截取积分余额 → commit+push 监控数据。

### 2. 每日定时 + 远程触发（一次性安装）

双击 `setup_task.bat`，注册两个计划任务（当前用户，无需管理员）：

- `YuanbaoCheckinDaily` — 每天 00:00 + RandomDelay 0~2h，经 `run_daily.vbs` 用
  `pythonw` 无窗口执行（错过时刻开机后自动补跑）。
- `YuanbaoRemoteTrigger` — 每 1 分钟运行 `remote_listener.py --once`。

删除/查看: `python setup_task.py --remove` / `--query`。

### 3. 远程触发（手机浏览器即可）

打开监控页上的 **⚡ 立即远程触发** 按钮（直达
`github.com/imiuim/yuanbao-checkin/edit/main/docs/trigger.json`），
把 `"run": false` 改成 `"run": true`，Commit changes 即可。
监听器 60 秒内拉起打卡，执行完自动回写 `run: false` 与结果；
触发请求 24 小时未处理自动作废。全程不暴露电脑端口，凭据复用 git 推送的同一份。

### 4. Web 监控页

**https://imiuim.github.io/yuanbao-checkin/**（仓库 `docs/` 目录，Pages 分支部署）

展示：账号 + 积分余额截图（每次运行更新）、六个任务状态、今日是否已运行、
远程触发入口与上次触发结果、最近 60 条运行日志。本地预览:
`python -m http.server -d docs 8000`。

## 踩坑记录（重要）

1. **任务计数看入口**：必须从福利中心页面的"去XX"按钮进入才会计数；从聊天主界面工具栏进入同一功能（拍题答疑等）不计入。
2. **H5 页面**：福利中心是 WebView，uiautomator 拿不到内部控件，全部坐标点击。
3. **打卡不即时刷新**：点击第1天卡片后页面可能仍显示"已打卡 0 天"，重进福利页才刷新。
4. **生成开始即计数**：AI 生成不必等完成，开始生成后即可返回（写作/拍题均验证过）。
5. **中文输入**：`adb shell input text` 不支持中文，写作主题用英文。
6. **计划任务 XML**：`RandomDelay` 只能用 XML 注册（schtasks 命令行不支持）；
   XML 元素顺序有 schema 约束（Repetition 在 Enabled 前，ExecutionTimeLimit 在 Enabled 后）。
7. **GitHub API**：中文 JSON 别放命令行 `-d`（编码损坏），写 UTF-8 文件再 `-d @file`。

## 项目结构

```
yuanbao-checkin/
├── yuanbao_checkin.py    # 主脚本（纯 ADB, 依赖 Pillow 裁积分截图）
├── remote_listener.py    # 远程触发监听器（GitHub API 轮询 trigger.json）
├── setup_task.py/.bat    # 注册计划任务（XML 支持 RandomDelay）
├── run_daily.vbs         # 每日任务无窗口启动器
├── config.ini            # 账号名等配置
├── assets/q1..q3.png     # 拍题用题目图（每轮推送到手机相册）
├── docs/index.html       # Web 监控页（GitHub Pages）
├── docs/status.json      # 运行状态（脚本生成, 监控页读取）
├── docs/points.png       # 积分余额截图（脚本生成）
├── docs/trigger.json     # 远程触发开关（监听器轮询/回写）
└── logs/                 # 运行截屏留档（gitignore）
```

## License

MIT
