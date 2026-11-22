@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0_detect_steam.bat"
if not defined STEAMDIR (
  echo [错误] 找不到 Steam 安装目录。请设置环境变量 STEAM_PATH。
  pause
  exit /b 1
)
REM ============================================
REM  ost_toggle.bat —— 一键开关 OpenSteamTool
REM  必须先完全退出 Steam 再操作！
REM ============================================
echo.
echo  ============================================
echo   OpenSteamTool 开关  (Steam: %STEAMDIR%)
echo   注意：操作前请先在 Steam 里"退出"，任务管理器确认 steam.exe 没了
echo  ============================================
echo.
echo   [1] 启用 (装dll，开始解锁)
echo   [2] 禁用 (移走dll，恢复纯净Steam，防封号)
echo.
set /p OPT=请选择 1 或 2:

tasklist /FI "IMAGENAME eq steam.exe" 2>nul | find /i "steam.exe" >nul
if %errorlevel%==0 (
  echo.
  echo [错误] Steam 还在运行！请先完全退出 Steam 再运行本工具。
  pause
  exit /b 1
)

if "%OPT%"=="1" goto ENABLE
if "%OPT%"=="2" goto DISABLE
echo 无效选择
pause
exit /b 1

:ENABLE
echo [启用] 复制 DLL 到 %STEAMDIR% ...
copy /Y "%~dp0ost_dll\dwmapi.dll" "%STEAMDIR%\dwmapi.dll" >nul
copy /Y "%~dp0ost_dll\xinput1_4.dll" "%STEAMDIR%\xinput1_4.dll" >nul
copy /Y "%~dp0ost_dll\OpenSteamTool.dll" "%STEAMDIR%\OpenSteamTool.dll" >nul
echo [完成] 已启用。现在启动 Steam 即可。
pause
exit /b 0

:DISABLE
echo [禁用] 从 %STEAMDIR% 移走 DLL（回归纯净Steam）...
del /F /Q "%STEAMDIR%\dwmapi.dll" 2>nul
del /F /Q "%STEAMDIR%\xinput1_4.dll" 2>nul
del /F /Q "%STEAMDIR%\OpenSteamTool.dll" 2>nul
echo [完成] 已禁用。Steam 恢复原版，联机/VAC 游戏前请务必先执行这一步。
pause
exit /b 0
