' 元宝每日打卡 - 隐藏窗口启动器（供 Windows 计划任务调用）
' 说明: pythonw 不弹控制台; wscript 本身也无窗口。
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir

' 后台执行打卡脚本, 不等待
sh.Run "pythonw yuanbao_checkin.py", 0, False
