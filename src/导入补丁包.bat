@echo off
chcp 65001 >nul
title 导入补丁包 - 覆盖进游戏目录(带备份)
cd /d "%~dp0"

REM Python：优先 PATH 里的 python，其次 py 启动器
set "PY=python"
where python >nul 2>&1 || (where py >nul 2>&1 && set "PY=py")
set "SCRIPT=%~dp0apply_patch.py"

echo ============================================================
echo   导入补丁包  -  按目录结构覆盖进游戏目录 (覆盖前自动备份)
echo ============================================================
echo.

if "%~1"=="" (
  echo 用法：把 补丁包.zip 或 解压后的文件夹，直接拖到本 bat 图标上。
  echo 注意：要等游戏【下载完成】后再覆盖，否则会被下载冲掉。
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
echo 补丁包路径: %PKG%
echo.

set "APPID=3489700"
set /p "APPID=输入游戏 AppID（直接回车 = 剑星 3489700）: "

echo.
echo 正在覆盖，请稍候...
echo ------------------------------------------------------------
"%PY%" "%SCRIPT%" %APPID% "%PKG%"
echo ------------------------------------------------------------
echo.
echo 完成。破解文件已覆盖进游戏目录（原文件备份在游戏目录\_patch_backup\）。
echo.
pause >nul
