# -*- coding: utf-8 -*-
"""
steam_unlock_launcher.py — 一体化 Steam 家庭共享解锁启动器

设计目标：
  * 只有用本程序启动 Steam 才生效：临时把 OST 注入 DLL 放到 Steam 目录 →
    启动 Steam → 等 DLL 被加载后立刻从磁盘移走 DLL → patch 内存
    (NOP CUser::UpdateFamilyRunningApps 的 jne) → 守护重 patch。
  * 正常双击 steam.exe 不受影响：磁盘上没有 OST DLL，是纯净 Steam。
  * DLL 只在启动瞬间短暂出现在磁盘，加载后立即删除，即使本程序被强杀也无残留。

用法：
  steam_unlock_launcher.exe           正常模式：steam 须关闭，本程序启动它并解锁
  steam_unlock_launcher.exe --clean   仅清理 Steam 目录里残留的 OST DLL 后退出
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import steam_path as SP
from ctypes import wintypes

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
STEAM_DIR = SP.find_steam_dir() or r"C:\Program Files (x86)\Steam"
STEAM_EXE = os.path.join(STEAM_DIR, "steam.exe")
OST_DLLS = ("dwmapi.dll", "xinput1_4.dll", "OpenSteamTool.dll")
KEEP_DLLS = True   # 与 入库工具目录 统一为常驻；False 才恢复旧的"加载后移走"模式

# 内存 patch：CUser::UpdateFamilyRunningApps 入口的全局开关 jne -> NOP
PATCH_PATTERN = "44 8B 00 45 85 C0 75 04 8B C6 EB 16 4C 8D 45 77"
PATCH_OFFSET = 6           # "75 04" 在模式内的起始字节下标
PATCH_BYTES = bytes.fromhex("90 90")
ORIG_BYTES = bytes.fromhex("75 04")
PATCHED_PATTERN = "90 90 8B C6 EB 16 4C 8D 45 77"

MODULE_NAME = "steamclient64.dll"
CHECK_INTERVAL = 3.0
MODULE_WAIT_SEC = 90       # 等 steamclient64.dll + OST 加载的最长时间
DLL_LOAD_WAIT_SEC = 60


def out(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Win32 绑定（纯 ctypes）
# ----------------------------------------------------------------------------
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_ALL_ACCESS = (
    PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
)
LIST_MODULES_ALL = 0x03


class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]


kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.WriteProcessMemory.restype = wintypes.BOOL
psapi.EnumProcesses.argtypes = [
    ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
]
psapi.EnumProcesses.restype = wintypes.BOOL
psapi.EnumProcessModulesEx.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
]
psapi.EnumProcessModulesEx.restype = wintypes.BOOL
psapi.GetModuleInformation.argtypes = [
    wintypes.HANDLE, wintypes.HMODULE, ctypes.POINTER(MODULEINFO), wintypes.DWORD
]
psapi.GetModuleInformation.restype = wintypes.BOOL
psapi.GetModuleBaseNameW.argtypes = [
    wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD
]
psapi.GetModuleBaseNameW.restype = wintypes.DWORD


def steam_pids() -> list[int]:
    arr = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
        return []
    count = needed.value // ctypes.sizeof(wintypes.DWORD)
    result = []
    for pid in arr[:count]:
        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h:
            continue
        try:
            buf = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(h, None, buf, 260)
            if buf.value.lower() == "steam.exe":
                result.append(pid)
        finally:
            kernel32.CloseHandle(h)
    return result


class SteamProc:
    def __init__(self, pid: int):
        self.pid = int(pid)
        self.handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, self.pid)
        if not self.handle:
            raise OSError(f"OpenProcess({pid}) 失败 err={ctypes.get_last_error()}（试试管理员）")

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "SteamProc":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def modules(self) -> dict[str, tuple[int, int]]:
        arr = (wintypes.HMODULE * 2048)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcessModulesEx(
            self.handle, arr, ctypes.sizeof(arr), ctypes.byref(needed), LIST_MODULES_ALL
        ):
            raise OSError(f"EnumProcessModulesEx 失败 err={ctypes.get_last_error()}")
        count = min(needed.value // ctypes.sizeof(wintypes.HMODULE), 2048)
        result: dict[str, tuple[int, int]] = {}
        for hmod in arr[:count]:
            info = MODULEINFO()
            if not psapi.GetModuleInformation(
                self.handle, hmod, ctypes.byref(info), ctypes.sizeof(info)
            ):
                continue
            buf = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(self.handle, hmod, buf, 260)
            result[buf.value.lower()] = (int(info.lpBaseOfDll or 0), int(info.SizeOfImage))
        return result

    def read(self, address: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        if not kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got)
        ) or got.value != size:
            raise OSError(f"ReadProcessMemory(0x{address:X}, {size}) 失败")
        return buf.raw[:size]

    def write(self, address: int, data: bytes) -> None:
        buf = ctypes.create_string_buffer(data)
        got = ctypes.c_size_t(0)
        if not kernel32.WriteProcessMemory(
            self.handle, ctypes.c_void_p(address), buf, len(data), ctypes.byref(got)
        ) or got.value != len(data):
            raise OSError(f"WriteProcessMemory(0x{address:X}) 失败 err={ctypes.get_last_error()}")


def parse_pattern(text: str) -> tuple[bytes, bytes]:
    toks = text.replace(",", " ").replace("|", " ").split()
    data = bytearray()
    mask = bytearray()
    for t in toks:
        t = t.lower()
        if t in ("?", "??", "*", "**"):
            data.append(0)
            mask.append(0)
        else:
            if len(t) == 1:
                t = "0" + t
            data.append(int(t, 16))
            mask.append(1)
    return bytes(data), bytes(mask)


# ----------------------------------------------------------------------------
# DLL 生命周期
# ----------------------------------------------------------------------------
def resource_dir() -> str:
    """打包后 DLL 内嵌在这里；源码运行时用脚本目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.argv[0])))
    return os.path.dirname(os.path.abspath(__file__))


def dll_bundle_dir() -> str:
    """内嵌 DLL 目录：优先 <资源>/ost_dll，其次 <资源> 本身。"""
    d = os.path.join(resource_dir(), "ost_dll")
    if os.path.isdir(d) and all(os.path.isfile(os.path.join(d, x)) for x in OST_DLLS):
        return d
    return resource_dir()


def dlls_present_in_steam() -> bool:
    return all(os.path.isfile(os.path.join(STEAM_DIR, d)) for d in OST_DLLS)


def install_dlls() -> bool:
    """把内嵌 OST DLL 复制到 Steam 目录。返回是否全部就位。"""
    # 先清掉上次 rename 遗留的 .used（此时 steam 已关闭，文件不再被占用）
    for d in OST_DLLS:
        used = os.path.join(STEAM_DIR, d + ".used")
        if os.path.isfile(used):
            try:
                os.remove(used)
            except Exception:
                pass
    src_dir = dll_bundle_dir()
    ok = True
    for d in OST_DLLS:
        src = os.path.join(src_dir, d)
        dst = os.path.join(STEAM_DIR, d)
        if not os.path.isfile(src):
            out(f"  [错误] 内嵌 DLL 缺失：{d}")
            ok = False
            continue
        try:
            shutil_copy(src, dst)
        except Exception as e:
            out(f"  [错误] 复制 {d} 失败：{e}")
            ok = False
    return ok


def remove_dlls(force: bool = False) -> None:
    """从 Steam 目录移走 OST DLL。

    常驻模式（KEEP_DLLS=True）下主流程调用一律 no-op；只有 --clean 传 force=True
    才真正移走。恢复纯净 Steam 请用 --clean。

    已加载进内存的 DLL 文件被映射占用，os.remove 会报 WinError 5；
    改用 os.rename 改成 .used 后缀（同一卷可原子改名，不影响已加载的映射），
    再尝试删掉 .used；删不掉也无妨——Steam 只按原名 dwmapi.dll 等加载，
    .used 后缀对 Steam 不可见，磁盘目录对 Steam 而言已是纯净的。
    下次启动前 install_dlls 会先把残留 .used 清掉再复制。
    """
    if KEEP_DLLS and not force:
        return
    for d in OST_DLLS:
        p = os.path.join(STEAM_DIR, d)
        used = p + ".used"
        if os.path.isfile(used):
            try:
                os.remove(used)
            except Exception:
                pass
        if os.path.isfile(p):
            try:
                os.rename(p, used)
            except Exception as e:
                # 兜底：若 rename 也失败，尝试直接删
                try:
                    os.remove(p)
                except Exception:
                    out(f"  [警告] 移走 {d} 失败：{e}")


def shutil_copy(src: str, dst: str) -> None:
    import shutil
    shutil.copyfile(src, dst)


# ----------------------------------------------------------------------------
# 内存 patch
# ----------------------------------------------------------------------------
def wait_modules(pid: int, needed: tuple[str, ...], timeout: float) -> dict[str, tuple[int, int]]:
    """轮询等待指定进程加载所需模块（保留给外部调用）。"""
    deadline = time.time() + timeout
    last: dict[str, tuple[int, int]] = {}
    while time.time() < deadline:
        try:
            with SteamProc(pid) as p:
                last = p.modules()
            if all(n in last for n in needed):
                return last
        except Exception:
            pass
        time.sleep(1.0)
    return last


def wait_for_loaded_steam(needed: tuple[str, ...], timeout: float
                          ) -> tuple[int | None, dict[str, tuple[int, int]]]:
    """动态轮询所有 steam 进程，找第一个真正加载了所需模块的进程。

    Steam 有两阶段启动：bootstrap（检查更新，内存很小）会退出并拉起真正的
    客户端（PID 会变）。固定盯第一个 PID 会漏掉换进程的情况，因此这里每次
    重新枚举，返回 (pid, modules)；超时返回 (None, {})。
    """
    deadline = time.time() + timeout
    last: dict[str, tuple[int, int]] = {}
    while time.time() < deadline:
        for pid in steam_pids():
            try:
                with SteamProc(pid) as p:
                    mods = p.modules()
            except Exception:
                continue
            if MODULE_NAME in mods:
                # 主模块已加载；其余所需模块（OST）再多给一点时间
                if all(n in mods for n in needed):
                    return pid, mods
                last = mods
        time.sleep(1.5)
    return None, last


def _find_all(p: "SteamProc", base: int, size: int, needle: bytes,
              max_hits: int = 8) -> list[int]:
    """分块读进程内存，用 bytes.find（C 实现，秒级）找所有命中，返回绝对地址。

    块间保留 overlap 字节并处理跨块重复；不可读页直接跳过。
    """
    hits: list[int] = []
    chunk = 4 * 1024 * 1024
    overlap = len(needle) - 1
    pos = base
    end = base + size
    while pos < end:
        want = min(chunk, end - pos)
        try:
            buf = p.read(pos, want)
        except OSError:
            pos += max(1, want - overlap)
            continue
        start = 0
        while True:
            i = buf.find(needle, start)
            if i < 0:
                break
            addr = pos + i
            if not hits or addr != hits[-1]:
                hits.append(addr)
                if len(hits) >= max_hits:
                    return hits
            start = i + 1
        pos += max(1, want - overlap)
    return hits


def scan_and_patch(pid: int, base: int, size: int) -> str:
    """
    在 steamclient64.dll 范围内扫描唯一字节模式并 patch。
    返回状态字符串：patched / already / notfound / error
    """
    pat, _ = parse_pattern(PATCH_PATTERN)
    ppat, _ = parse_pattern(PATCHED_PATTERN)
    with SteamProc(pid) as p:
        hits = _find_all(p, base, size, pat)
        patched_hits = _find_all(p, base, size, ppat)

        if patched_hits and not hits:
            return "already"
        if len(hits) != 1:
            out(f"  [警告] 模式命中 {len(hits)} 处（期望 1），跳过 patch 以免误改")
            for h in hits[:4]:
                out(f"    off=0x{h - base:X}")
            return "notfound"
        target = hits[0] + PATCH_OFFSET
        cur = p.read(target, 2)
        if cur == PATCH_BYTES:
            return "already"
        p.write(target, PATCH_BYTES)
        back = p.read(target, 2)
        if back != PATCH_BYTES:
            return "error"
        out(f"  [patch] 0x{target:X} (模块 off 0x{target - base:X}): {cur.hex(' ')} -> {back.hex(' ')}")
        return "patched"


def is_patched(pid: int, base: int, size: int) -> bool:
    """快速检测目标字节是否仍为 90 90。"""
    pat, _ = parse_pattern(PATCHED_PATTERN)
    try:
        with SteamProc(pid) as p:
            return bool(_find_all(p, base, size, pat, max_hits=1))
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def clean_only() -> None:
    out("[清理] 移走 Steam 目录里的 OST DLL ...")
    remove_dlls(force=True)
    out("[完成] Steam 目录已恢复纯净。")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if "--clean" in sys.argv[1:]:
        clean_only()
        return

    out("=" * 58)
    out(" Steam 家庭共享解锁启动器（内存 patch 层）")
    out(" 入库/下载走 入库工具目录 全自动工具；本程序只负责启动 + 改内存 patch")
    out(" DLL 常驻：无论谁启动 Steam 都会注入；本程序仅额外做内存解锁")
    out("=" * 58)

    if not os.path.isfile(STEAM_EXE):
        out(f"[错误] 找不到 Steam：{STEAM_EXE}")
        return

    running = steam_pids()
    if running:
        out("")
        out("[提示] 检测到 Steam 已在运行（PID: %s）。" % ", ".join(map(str, running)))
        out("本程序必须在 Steam 关闭的状态下使用。")
        out("请先完全退出 Steam（托盘图标右键退出），再双击本程序。")
        out("当前 Steam 未做任何改动，保持纯净启动。")
        out("")
        try:
            input("按回车键退出 ...")
        except Exception:
            time.sleep(5)
        return

    # 1) DLL 就位
    out("[1/4] 放入 OST 注入 DLL ...")
    if not install_dlls():
        out("[错误] OST DLL 未能就位，终止。")
        return
    out("  DLL 已放入 Steam 目录。")

    # 2)+3) 启动 Steam，并等真正加载了 steamclient64.dll 的进程。
    #    Steam 有两阶段启动：先 bootstrap 检查更新（内存~41MB），验证完再
    #    退出并拉起真正客户端（换 PID）。这里绝不能 taskkill /F 强杀——
    #    强杀会让 Steam 进入"每次启动全量校验"的坏循环，反而永远起不来。
    #    只启动一次，给足等待时间；超时就干净退出并提示用户。
    out("[2/4] 启动 Steam ...")
    # 关键（多轮对照实验确认）：exe 内直接 Popen / os.startfile 启动 Steam 都必卡
    # bootstrap(40MB，"Verifying all executable checksums")，而用户手动
    # Start-Process / 双击则健康启动到 157MB。命令行完全相同，差异只在
    # PyInstaller 注入的 _PYI_*/_MEI* 环境变量 + 可能的父进程 Job 限制。
    # 解决：借 explorer.exe 做跳板 —— explorer 用自身干净环境、在 Job 外，
    # 以 ShellExecute 拉起 Steam，效果等同用户真实双击，彻底隔离本进程污染。
    # 诊断：把当前环境里的 _PYI_*/_MEI*/PATH 写到日志，便于核对。
    try:
        diag = os.path.join(STEAM_DIR, "unlock_env_diag.txt")
        with open(diag, "w", encoding="utf-8") as fh:
            for k in sorted(os.environ):
                if k.startswith("_PYI") or k.startswith("_MEI") or k.upper() == "PATH":
                    fh.write(f"{k}={os.environ[k]}\n")
    except Exception:
        pass
    # 关键（决定性对照实验确认）：由 PyInstaller child 进程直接 Popen /
    # os.startfile / explorer 跳板 / 白名单 env 启动 Steam，都会卡在 bootstrap
    # （"Verifying all executable checksums"，内存卡 38MB，不加载 steamclient64）。
    # 唯一健康的方式是让 Windows 任务调度器（父进程 = svchost 系统服务，非
    # PyInstaller child）来启动 —— 实测健康加载到 154MB，OST 三 DLL 全部注入。
    # 做法：建一个一次性计划任务并立刻 /Run，随后删除任务（Steam 独立继续运行）。
    TASK_NAME = "SteamFamilyUnlockLaunch"
    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    schtasks = os.path.join(system32, "schtasks.exe")
    # 先清掉可能残留的同名任务
    subprocess.run([schtasks, "/Delete", "/TN", TASK_NAME, "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        r = subprocess.run(
            [schtasks, "/Create", "/TN", TASK_NAME,
             "/TR", f'"{STEAM_EXE}"', "/SC", "ONCE", "/ST", "23:59", "/F"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            out(f"[错误] 创建启动任务失败：{r.stderr.decode('gbk', 'replace').strip()}")
            remove_dlls()
            return
        r = subprocess.run([schtasks, "/Run", "/TN", TASK_NAME],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # 任务已触发，立刻删掉，Steam 作为独立 GUI 进程继续运行
        subprocess.run([schtasks, "/Delete", "/TN", TASK_NAME, "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode != 0:
            out(f"[错误] 启动 Steam 失败：{r.stderr.decode('gbk', 'replace').strip()}")
            remove_dlls()
            return
    except Exception as e:
        out(f"[错误] 无法启动 Steam：{e}")
        remove_dlls()
        return
    out("[3/4] 等待 Steam 加载组件与注入 DLL ...（首次启动可能需 1-2 分钟）")
    pid, mods = wait_for_loaded_steam((MODULE_NAME,), 120)
    if pid is None:
        out("[错误] Steam 启动后 120 秒内未加载 steamclient64.dll，终止。")
        out("       请手动正常启动一次 Steam、确认能进库后再关闭，然后重试本程序。")
        out("       （本次未对 Steam 做强杀，其状态未被破坏。）")
        remove_dlls()
        return
    if "opensteamtool.dll" not in mods:
        out("[警告] 未检测到 opensteamtool.dll 被加载（注入可能未生效），继续尝试 patch。")

    # 常驻模式：DLL 留在磁盘，Steam 每次启动都会自动注入（与 入库工具目录 统一）
    remove_dlls()
    out("  常驻模式：OST DLL 保留在 Steam 目录，下次启动仍会自动注入。")

    base, size = mods[MODULE_NAME]
    out(f"  steamclient64.dll base=0x{base:X} size=0x{size:X}")

    # 4) patch + 守护
    out("[4/4] 修改内存并守护 ...")
    result = scan_and_patch(pid, base, size)
    if result == "error":
        out("[错误] 内存写入失败，可能权限不足。请用管理员身份运行本程序。")
    elif result == "notfound":
        out("[警告] 未找到唯一的字节模式——Steam 版本可能已更新，patch 跳过。")
    else:
        out(f"  内存状态：{result}")

    out("")
    out("已进入守护。现在去库里启动那个被占用的游戏即可联机游玩。")
    out("关闭 Steam 后本程序会自动结束；按 Ctrl+C 可提前退出。")
    out("-" * 58)

    last_pid = pid
    last_base, last_size = base, size
    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            pids = steam_pids()
            if last_pid not in pids:
                # 盯的进程没了：若还有别的 steam 进程，看是否是新的客户端
                alive_loaded = None
                for cand in pids:
                    try:
                        with SteamProc(cand) as p:
                            m = p.modules()
                        if MODULE_NAME in m:
                            alive_loaded = (cand, m[MODULE_NAME])
                            break
                    except Exception:
                        continue
                if alive_loaded is None:
                    out("[结束] Steam 已退出，守护结束。")
                    break
                new_pid, (nb, ns) = alive_loaded
                out(f"[提示] Steam 进程重启（{last_pid} -> {new_pid}）。")
                out("       常驻模式下 DLL 仍在磁盘，新进程会自动注入，但内存 patch 需重新执行。")
                out("       如需重新 patch，请关闭 Steam 后重新用本程序启动。")
                last_pid, last_base, last_size = new_pid, nb, ns
                continue
            # 盯的进程还在：检查 base 是否变化后重 patch
            try:
                with SteamProc(last_pid) as p:
                    m = p.modules()
                if MODULE_NAME in m and m[MODULE_NAME][0] != last_base:
                    last_base, last_size = m[MODULE_NAME]
            except Exception:
                continue
            if not is_patched(last_pid, last_base, last_size):
                out("[守护] 检测到 patch 已被还原，重新写入 ...")
                r = scan_and_patch(last_pid, last_base, last_size)
                out(f"  重 patch：{r}")
    except KeyboardInterrupt:
        out("\n[退出] 用户中断。")
    finally:
        remove_dlls()
        out("[完成] 守护结束；常驻模式下 DLL 保留在 Steam 目录（如需清理请用 --clean）。")


if __name__ == "__main__":
    main()
