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


def stop_steam(timeout=4):
    """优雅关 Steam（含子进程），超时强杀。返回 killed 进程名列表。"""
    targets = ("steam.exe", "steamwebhelper.exe", "crashhandler.exe")
    killed = []
    for graceful in (False, True):
        for name in targets:
            args = ["taskkill", "/IM", name, "/T"]
            if graceful:
                args.append("/F")
            try:
                r = subprocess.run(args, capture_output=True, text=True, timeout=10)
                if r.returncode == 0 and name not in killed:
                    killed.append(name)
            except Exception:
                pass
        if graceful:
            break
        # 等优雅退出生效；仍存活才强杀
        try:
            out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10).stdout.lower()
            if not any(n in out for n in targets):
                break
        except Exception:
            pass
        import time as _t
        _t.sleep(timeout)
    # 二次强杀兜底
    for name in targets:
        try:
            r = subprocess.run(["taskkill", "/IM", name, "/T", "/F"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and name not in killed:
                killed.append(name)
        except Exception:
            pass
    return {"killed": killed}


def clear_appinfo(steam_dir=None):
    """备份并删除 appinfo.vdf + appinfo/ 目录，冷启动前清缓存。"""
    steam_dir = steam_dir or find_steam_dir()
    result = {"removed": False, "backup_path": ""}
    if not steam_dir:
        return result
    appcache = os.path.join(steam_dir, "appcache")
    vdf = os.path.join(appcache, "appinfo.vdf")
    idir = os.path.join(appcache, "appinfo")
    existed = os.path.isfile(vdf) or os.path.isdir(idir)
    if not existed:
        return result
    import shutil as _sh
    from datetime import datetime as _dt
    backup_root = os.path.join(writable_dir(), "backup")
    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_root, "appinfo_%s" % stamp)
    try:
        os.makedirs(dst, exist_ok=True)
        if os.path.isfile(vdf):
            _sh.copy2(vdf, os.path.join(dst, "appinfo.vdf"))
        if os.path.isdir(idir):
            _sh.copytree(idir, os.path.join(dst, "appinfo"), dirs_exist_ok=True)
        result["backup_path"] = dst
    except Exception:
        pass
    try:
        if os.path.isfile(vdf):
            os.remove(vdf)
        if os.path.isdir(idir):
            _sh.rmtree(idir)
        result["removed"] = True
    except Exception:
        pass
    return result


def start_steam(steam_dir=None):
    """冷启动 Steam。返回是否成功拉起与 PID。"""
    steam_dir = steam_dir or find_steam_dir()
    if not steam_dir:
        return {"started": False, "pid": None}
    exe = os.path.join(steam_dir, "steam.exe")
    if not os.path.isfile(exe):
        exe = os.path.join(steam_dir, "Steam.exe")
    try:
        p = subprocess.Popen([exe], cwd=steam_dir)
        return {"started": True, "pid": p.pid}
    except Exception:
        return {"started": False, "pid": None}
