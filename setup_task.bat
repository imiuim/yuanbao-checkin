@echo off
rem 注册每日计划任务（无窗口运行）。需要以当前用户权限执行一次。
rem 任务名: YuanbaoCheckinDaily  每天 09:10 触发

set SCRIPT_DIR=%~dp0
schtasks /Create /F /TN "YuanbaoCheckinDaily" ^
  /TR "wscript.exe \"%SCRIPT_DIR%run_daily.vbs\"" ^
  /SC DAILY /ST 09:10

if %errorlevel%==0 (
  echo 已注册计划任务 YuanbaoCheckinDaily ^(每天 09:10, 隐藏窗口^)
) else (
  echo 注册失败, 请以管理员或当前用户权限重试。
)
pause
