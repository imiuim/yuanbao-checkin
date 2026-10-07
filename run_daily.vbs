' 元宝每日打卡 - 隐藏窗口启动器（由 setup_task.py 生成, 勿手改）
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "G:\vp\yuanbao-checkin"
sh.Run """D:\anaconda3\pythonw.exe"" yuanbao_checkin.py", 0, False
