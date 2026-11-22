@echo off
chcp 65001 >nul
title OpenSteamTool - 联机模式启动 Steam
call "%~dp0_detect_steam.bat"
if not defined STEAMDIR (
  echo [错误] 找不到 Steam 安装目录。请设置环境变量 STEAM_PATH。
  pause
  exit /b 1
)
set "STEAMEXE=%STEAMDIR%\steam.exe"
REM 以 -onlinefix 参数启动 Steam，启用 480 appid 大厅联机。同一时间只能一个此类联机游戏。
tasklist /FI "IMAGENAME eq steam.exe" 2>nul | find /i "steam.exe" >nul
if %errorlevel%==0 (
  echo [提示] Steam 已在运行。若要应用 -onlinefix，请先完全退出 Steam。
  choice /C YN /M "仍要继续启动另一个实例吗"
  if errorlevel 2 exit /b 0
)
echo [启动] %STEAMEXE% -onlinefix
start "" "%STEAMEXE%" -onlinefix
echo [完成] 已发出启动命令。到库中点游戏即可联机。
timeout /t 3 >nul
