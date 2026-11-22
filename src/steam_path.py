# -*- coding: utf-8 -*-
"""
steam_path.py —— 统一路径探测（可移植核心）

替代所有硬编码的 D:\\STEAM / D:\\STEAM入库。探测优先级：
  1. 环境变量 STEAM_PATH（用户可手动指定，最高优先级）
  2. 注册表 HKCU\\Software\\Valve\\Steam\\SteamPath
  3. 注册表 HKLM\\...\\Valve\\Steam\\InstallPath
  4. 当前运行的 steam.exe 进程路径（最贴近真实安装位置）
  5. 常见安装目录兜底

部署目录（key 库 / 缓存 / 配置存放处）用脚本自身位置：
  - 源码运行：__file__ 所在目录
  - PyInstaller onefile：sys.executable 所在目录（不是 _MEIPASS 临时目录）
"""
import os
import sys

_cached_steam_dir = None
_cached_deploy_dir = None

COMMON_STEAM_DIRS = [
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
    r"D:\Steam",
    r"D:\STEAM",
    r"E:\Steam",
    r"E:\STEAM",
    os.path.expandvars(r"%LOCALAPPDATA%\Steam"),
]


def _norm(p):
    if not p:
        return None
    p = os.path.expandvars(os.path.expanduser(str(p).strip().strip('"')))
    p = os.path.normpath(p)
    return p if os.path.isdir(p) else None


def _from_registry():
    """从注册表读 Steam 安装路径。"""
    try:
        import winreg
    except ImportError:
        return None
    queries = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]
    for hive, sub, name in queries:
        try:
            with winreg.OpenKey(hive, sub) as k:
                val, _ = winreg.QueryValueEx(k, name)
                d = _norm(val)
                if d and os.path.isfile(os.path.join(d, "steam.exe")):
                    return d
        except Exception:
            continue
    return None


def _from_running_process():
    """从运行中的 steam.exe 进程拿可执行文件路径。"""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        arr = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
            return None
        count = needed.value // ctypes.sizeof(wintypes.DWORD)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        for pid in arr[:count]:
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                continue
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                if ok and buf.value.lower().endswith("steam.exe"):
                    d = _norm(os.path.dirname(buf.value))
                    if d:
                        return d
            except Exception:
                pass
            finally:
                kernel32.CloseHandle(h)
    except Exception:
        pass
    return None


def find_steam_dir(explicit=None):
    """返回 Steam 安装目录（含 steam.exe）。找不到返回 None。"""
    global _cached_steam_dir
    if explicit:
        d = _norm(explicit)
        if d and os.path.isfile(os.path.join(d, "steam.exe")):
            return d
    if _cached_steam_dir:
        return _cached_steam_dir
    # 1) 环境变量
    d = _norm(os.environ.get("STEAM_PATH"))
    if d and os.path.isfile(os.path.join(d, "steam.exe")):
        _cached_steam_dir = d
        return d
    # 2) 注册表
    d = _from_registry()
    if d:
        _cached_steam_dir = d
        return d
    # 3) 运行中的进程
    d = _from_running_process()
    if d:
        _cached_steam_dir = d
        return d
    # 4) 常见目录
    for p in COMMON_STEAM_DIRS:
        d = _norm(p)
        if d and os.path.isfile(os.path.join(d, "steam.exe")):
            _cached_steam_dir = d
            return d
    return None


def get_steam_dir_or_raise():
    d = find_steam_dir()
    if not d:
        raise RuntimeError(
            "找不到 Steam 安装目录。请设置环境变量 STEAM_PATH 指向含 steam.exe 的目录。"
        )
    return d


def get_lua_path():
    """返回 mygames.lua 完整路径（Steam 实际用的是 config\\stplug-in）。"""
    return os.path.join(get_steam_dir_or_raise(), "config", "stplug-in", "mygames.lua")


def app_dir():
    """脚本/exe 所在目录（真实的，不是 _MEIPASS）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_deploy_dir():
    """部署目录：存放 key 库/缓存/配置。优先找已有 key 库的目录，否则用脚本目录。"""
    global _cached_deploy_dir
    if _cached_deploy_dir:
        return _cached_deploy_dir
    base = app_dir()
    candidates = [
        base,
        os.path.dirname(base),
        os.path.join(os.path.dirname(base), "ost_deploy"),
        os.path.join(base, "ost_deploy"),
    ]
    seen = set()
    for d in candidates:
        d = os.path.normpath(d)
        if d in seen:
            continue
        seen.add(d)
        if os.path.isfile(os.path.join(d, "depotkeys_master.json")):
            _cached_deploy_dir = d
            return d
    # 没找到就放脚本目录，首次运行会自动下载 key 库到这里
    _cached_deploy_dir = base
    return base


if __name__ == "__main__":
    print("Steam 目录 :", find_steam_dir())
    print("Lua 路径   :", get_lua_path() if find_steam_dir() else "(未找到 Steam)")
    print("部署目录   :", get_deploy_dir())
