@echo off
chcp 65001 >nul
title OpenSteamTool 管理面板
cd /d "%~dp0"
call "%~dp0_detect_steam.bat"
if not defined STEAMDIR (
  echo [错误] 找不到 Steam 安装目录。请设置环境变量 STEAM_PATH 指向含 steam.exe 的目录。
  pause
  exit /b 1
)
REM Python：优先 py 启动器，其次 PATH 里的 python，最后常见安装路径
set "PY=python"
where python >nul 2>&1 || (where py >nul 2>&1 && set "PY=py")
set "HERE=%~dp0"
set "ADDGAME=%HERE%addgame_pro.py"
set "ADDALL=%HERE%addall.py"
set "TOGGLE=%HERE%ost_toggle.bat"

:MENU
cls
echo  ============================================================
echo   OpenSteamTool 管理面板   (Steam: %STEAMDIR%)
echo  ============================================================
echo.
echo   [1] 添加游戏入库 (输入名字或 AppID)
echo   [2] 批量导入本机已安装游戏 (addall --list)
echo   [3] 联机模式启动 Steam (-onlinefix)
echo   [4] 正常启动 Steam
echo   [5] 启用/禁用 OST 的 DLL (防封号开关)
echo   [6] 查看当前入库清单
echo   [0] 退出
echo.
set /p OPT=请选择:

if "%OPT%"=="1" goto ADDGAME
if "%OPT%"=="2" goto ADDALL
if "%OPT%"=="3" goto ONLINE
if "%OPT%"=="4" goto NORMAL
if "%OPT%"=="5" goto TOGGLE
if "%OPT%"=="6" goto LIST
if "%OPT%"=="0" exit /b 0
goto MENU

:ADDGAME
set /p G=游戏名或AppID:
"%PY%" "%ADDGAME%" %G%
pause
goto MENU

:ADDALL
"%PY%" "%ADDALL%" --list
echo.
set /p APPLY=写入全部? 输入 yes 确认:
if /i "%APPLY%"=="yes" "%PY%" "%ADDALL%" --apply
pause
goto MENU

:ONLINE
tasklist /FI "IMAGENAME eq steam.exe" 2>nul | find /i "steam.exe" >nul
if %errorlevel%==0 ( echo [提示] 请先完全退出 Steam 再启动联机模式。 & pause & goto MENU )
start "" "%STEAMDIR%\steam.exe" -onlinefix
echo [完成] 已用 -onlinefix 启动。
pause
goto MENU

:NORMAL
start "" "%STEAMDIR%\steam.exe"
echo [完成] 已正常启动。
pause
goto MENU

:TOGGLE
call "%TOGGLE%"
goto MENU

:LIST
echo  ===== %STEAMDIR%\config\stplug-in\mygames.lua =====
type "%STEAMDIR%\config\stplug-in\mygames.lua"
echo.
pause
goto MENU
