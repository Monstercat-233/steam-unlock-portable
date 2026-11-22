@echo off
chcp 65001 >nul
title 导入破解包 - 自动锁定历史版本
cd /d "%~dp0"

REM Python：优先 PATH 里的 python，其次 py 启动器
set "PY=python"
where python >nul 2>&1 || (where py >nul 2>&1 && set "PY=py")
set "SCRIPT=%~dp0version_lock.py"

echo ============================================================
echo   导入破解包  -  自动提老GID + 数字写法锁定历史版本
echo ============================================================
echo.

if "%~1"=="" (
  echo 用法：把 破解包.zip 或 解压后的文件夹，直接拖到本 bat 图标上。
  echo.
  pause
  exit /b
)

if not exist "%~1" (
  echo [错误] 路径不存在: %~1
  echo.
  pause
  exit /b
)

set "PKG=%~1"
echo 破解包路径: %PKG%
echo.

set "APPID=3489700"
set /p "APPID=输入游戏 AppID（直接回车 = 剑星 3489700）: "

echo.
echo 正在导入，请稍候...
echo ------------------------------------------------------------
"%PY%" "%SCRIPT%" %APPID% --import "%PKG%"
echo ------------------------------------------------------------
echo.
echo 完成。接下来：①关 Steam ②删 Steam安装目录\appcache\appinfo.vdf ③冷启动
echo ④确认 content_log 下载 GID 是锁定值 ⑤下完把补丁覆盖进游戏目录。
echo.
pause >nul
