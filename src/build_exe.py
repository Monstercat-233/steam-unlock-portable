# -*- coding: utf-8 -*-
"""把 steam_unlock_launcher.py 打包成单文件 exe，内嵌 OST 三 DLL。"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "steam_unlock_launcher.py")
OST_DIR = os.path.join(HERE, "ost_dll")
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")

NAME = "SteamFamilyUnlock"  # 内部英文名，交付时再重命名中文

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--console",  # 显示状态窗口，方便用户看到 patch 结果
    "--clean",
    "--name", NAME,
    "--distpath", DIST,
    "--workpath", BUILD,
    "--specpath", HERE,
]
# Windows 下每个 --add-data 用 "SOURCE:DEST"（PyInstaller 6 接受冒号）
for d in ("dwmapi.dll", "xinput1_4.dll", "OpenSteamTool.dll"):
    cmd += ["--add-data", f"{os.path.join(OST_DIR, d)}:ost_dll"]
cmd.append(SRC)

print("打包命令:")
print(" ".join(cmd))
print("-" * 60)
rc = subprocess.call(cmd, cwd=HERE)
print("-" * 60)
print("PyInstaller 退出码:", rc)
exe = os.path.join(DIST, NAME + ".exe")
if os.path.isfile(exe):
    print("EXE 已生成:", exe, os.path.getsize(exe), "bytes")
else:
    print("EXE 未生成")
