"""集中路径与账号解析：v2 全项目唯一的 Steam 路径来源，禁止其它模块硬编码路径。"""
import os
import re
import sys
import ctypes
import subprocess

_STEAM64_BASE = 76561197960265728


def steam64_to_accountid(steam64):
    return int(steam64) - _STEAM64_BASE


def resource_dir():
    """只读随包资源目录（key 库/json 随 exe 打包）。frozen=_MEIPASS，源码=src/。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def writable_dir():
    """运行时可写数据目录（names.json/snapshots/audit）。frozen=exe 同目录，源码=src/。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _reg_steam_path():
    try:
        import winreg
        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            val, _ = winreg.QueryValueEx(k, name)
                            if val:
                                return os.path.normpath(val)
                        except FileNotFoundError:
                            pass
            except OSError:
                continue
    except Exception:
        pass
    return None


def _process_steam_path():
    """从运行中 steam.exe 进程取可执行文件路径（标准库 ctypes 实现）。"""
    try:
        import winreg  # noqa: F401  # 确保仅在 Windows 上继续
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        ENUM = ctypes.wintypes.DWORD * 4096
        arr = ENUM()
        needed = ctypes.wintypes.DWORD()
        if not kernel32.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(needed)):
            return None
        count = needed.value // ctypes.sizeof(ctypes.wintypes.DWORD)
        for i in range(count):
            pid = arr[i]
            if not pid:
                continue
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                continue
            try:
                buf = ctypes.create_unicode_buffer(4096)
                size = ctypes.wintypes.DWORD(len(buf))
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    if os.path.basename(buf.value).lower() == "steam.exe":
                        return os.path.dirname(buf.value)
            finally:
                kernel32.CloseHandle(h)
    except Exception:
        pass
    return None


def _common_steam_dirs():
    roots = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "ProgramW6432"):
        p = os.environ.get(env)
        if p:
            roots.append(os.path.join(p, "Steam"))
    for drive in ("C", "D", "E", "F", "G"):
        roots.append(os.path.join(drive + ":\\", "Steam"))
        roots.append(os.path.join(drive + ":\\", "Program Files (x86)", "Steam"))
    return [r for r in roots if os.path.isdir(r)]


def find_steam_dir(explicit=None):
    if explicit:
        return os.path.normpath(explicit)
    env = os.environ.get("STEAM_PATH")
    if env:
        return os.path.normpath(env)
    for getter in (_reg_steam_path, _process_steam_path):
        p = getter()
        if p and os.path.isdir(p):
            return os.path.normpath(p)
    commons = _common_steam_dirs()
    if commons:
        return os.path.normpath(commons[0])
    return None


def lua_path():
    steam = find_steam_dir()
    if not steam:
        raise RuntimeError("找不到 Steam 安装目录；请设置环境变量 STEAM_PATH")
    return os.path.join(steam, "config", "stplug-in", "mygames.lua")


def _reg_autologinuser():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            val, _ = winreg.QueryValueEx(k, "AutoLoginUser")
            return val
    except Exception:
        return None


def list_accounts():
    """读 loginusers.vdf，返回 [{steam64, accountid, account_name, persona_name}]。"""
    steam = find_steam_dir()
    if not steam:
        return []
    vdf = os.path.join(steam, "config", "loginusers.vdf")
    if not os.path.isfile(vdf):
        return []
    try:
        text = open(vdf, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    # VDF 形如: "7656119..." { "AccountName" "xxx" "PersonaName" "yyy" }
    blocks = re.findall(r'"(\d{17})"\s*\{(.*?)\}', text, re.S)
    out = []
    for s64, body in blocks:
        def field(name):
            m = re.search(r'"' + re.escape(name) + r'"\s+"([^"]*)"', body)
            return m.group(1) if m else ""
        out.append({
            "steam64": s64,
            "accountid": steam64_to_accountid(s64),
            "account_name": field("AccountName"),
            "persona_name": field("PersonaName"),
        })
    return out


def current_account():
    name = _reg_autologinuser()
    if not name:
        return None
    for acc in list_accounts():
        if acc["account_name"] == name:
            return acc
    return None


def steam_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq steam.exe"],
            capture_output=True, text=True, timeout=10,
        ).stdout.lower()
        return "steam.exe" in out
    except Exception:
        return False
