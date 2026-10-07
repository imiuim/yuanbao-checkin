# yuanbao-checkin

腾讯元宝（com.tencent.hunyuan.app.chat）福利中心每日任务自动化脚本 + Web 监控页。

通过 ADB 模拟点击完成元宝"福利中心"的日常积分任务，运行后生成 `status.json` 供监控页展示。

## 已完成任务覆盖

| 任务 | 积分 | 方式 |
|---|---|---|
| 元宝能力站打卡 | 8000 | 点击"第1天"卡片 |
| 趣问元宝 ×3 | 1500 | 福利页"去提问"入口逐个提问 |
| 使用写作能力 ×3 | 1500 | "去写作"入口，输入英文主题生成 |
| 使用拍题能力 ×3 | 1500 | "去拍题"入口，相册选预置题目图 |
| 使用P图能力 ×3 | 1500 | "去P图"入口，自动选图（生成按钮需按日志截屏校准） |
| 参与体验优化计划 | 3000 | 打开活动页留档 |
| 邀2名新用户 | - | 需真实新用户，无法自动化，跳过 |

## 踩坑记录（重要）

1. **任务计数看入口**：必须从福利中心页面的"去XX"按钮进入才会计数；从聊天主界面工具栏进入同一功能（拍题答疑等）不计入。
2. **H5 页面**：福利中心是 WebView，uiautomator 拿不到内部控件，全部坐标点击。
3. **打卡不即时刷新**：点击第1天卡片后页面可能仍显示"已打卡 0 天"，重进福利页才刷新。
4. **生成开始即计数**：AI 生成不必等完成，开始生成后即可返回（写作/拍题均验证过）。
5. **中文输入**：`adb shell input text` 不支持中文，写作主题用英文。

## 使用

### 0. 前置

- `adb` 在 PATH 中；手机开启"无线调试"并配对连接：`adb connect 192.168.31.7:41681`
- 屏幕分辨率 1080x2400（Redmi 22127RK46C 已验证）。**其他分辨率需重新标定** `yuanbao_checkin.py` 中的 `COORDS`（开发者选项"指针位置"逐个核对）。
- 首次运行前确保元宝已登录。

### 1. 手动运行

```bash
python yuanbao_checkin.py                       # 全部任务
python yuanbao_checkin.py --only checkin ask    # 只跑指定任务
python yuanbao_checkin.py --device <serial>     # 指定设备
```

运行期间不要操作手机。日志与每步截屏在 `logs/`。

### 2. 每日定时（无窗口）

双击 `setup_task.bat` 注册计划任务（每天 09:10），通过 `run_daily.vbs` 用 `pythonw` 后台执行，不弹黑框。

### 3. Web 监控页

`docs/index.html` 读取同目录 `status.json`（脚本每次运行后更新），60 秒自动刷新。

- 本地预览：`python -m http.server -d monitor 8000` → http://127.0.0.1:8000
- GitHub Pages：仓库 Settings → Pages → Deploy from branch → `main` + `/docs`。
  脚本运行后 `git add docs/status.json && git commit && git push` 即可让线上监控页保持最新（可在计划任务后追加该命令）。

## 项目结构

```
yuanbao-checkin/
├── yuanbao_checkin.py   # 主脚本（纯 ADB, 无第三方依赖）
├── run_daily.vbs        # 计划任务无窗口启动器
├── setup_task.bat       # 注册每日计划任务
├── assets/q1..q3.png    # 拍题用题目图（推送到手机相册）
├── docs/index.html   # Web 监控页（自包含单文件）
├── docs/status.json  # 运行状态（脚本生成, 监控页读取）
└── logs/                # 运行截屏留档（gitignore）
```

## License

MIT
