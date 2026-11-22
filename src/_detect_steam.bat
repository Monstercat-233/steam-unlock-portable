@echo off
REM 探测 Steam 安装目录，结果写入环境变量 STEAMDIR。
REM 供其它 bat 用 call 调用（需在同一个 cmd 会话）。
set "STEAMDIR="
REM 1) 用户环境变量优先
if defined STEAM_PATH if exist "%STEAM_PATH%\steam.exe" set "STEAMDIR=%STEAM_PATH%"
REM 2) 注册表 HKCU\Software\Valve\Steam\SteamPath
if not defined STEAMDIR for /f "usebackq tokens=2,* skip=2" %%A in (`reg query "HKCU\Software\Valve\Steam" /v SteamPath 2^>nul`) do if exist "%%B\steam.exe" set "STEAMDIR=%%B"
REM 3) 注册表 HKLM（WOW6432Node）
if not defined STEAMDIR for /f "usebackq tokens=2,* skip=2" %%A in (`reg query "HKLM\SOFTWARE\WOW6432Node\Valve\Steam" /v InstallPath 2^>nul`) do if exist "%%B\steam.exe" set "STEAMDIR=%%B"
REM 4) 常见目录兜底
if not defined STEAMDIR if exist "C:\Program Files (x86)\Steam\steam.exe" set "STEAMDIR=C:\Program Files (x86)\Steam"
if not defined STEAMDIR if exist "D:\STEAM\steam.exe" set "STEAMDIR=D:\STEAM"
exit /b 0
