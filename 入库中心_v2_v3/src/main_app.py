# -*- coding: utf-8 -*-
"""入库中心 v2 —— pywebview（WebView2）界面层。

界面是唯一允许美化的层：后端 paths / auto_adapt / version_lock / apply_patch /
backup / game_index / update_guard / denuvo_helper 的行为与函数签名完全沿用，
所有文件路径一律经 paths.py 推导，界面资源走 resource_dir()，运行时可写状态走
writable_dir()。

前端是单文件 HTML（src/ui/index.html），通过 pywebview 的 js_api 桥调用下面的
Bridge；每个方法统一返回 {"ok": bool, "data": ..., "error": str}。

js_api 的每个调用由 pywebview 派发到独立工作线程，所以这里的耗时操作（联网、
解包、扫描）不会冻结界面；前端只需处理 Promise。
"""
import os
import re
import sys
import json
import logging
import threading

import paths as P
import auto_adapt as AA
import version_lock as V
import apply_patch as AP
import game_index as G
import backup as B
import update_guard as UG

try:  # 界面层依赖；缺失时 main() 给出明确提示而不是 ImportError 崩溃
    import webview
except Exception:  # pragma: no cover - 仅环境缺失时触发
    webview = None

MARK_FMT = "-- #OSTBLOCK:{}"
END_MARK = "-- #OSTENDBLOCK"

APP_TITLE = "入库中心 · OpenSteamTool 全自动 v2"
PREF_FILE = "ui_prefs.json"
LOG_FILE = "ui_error.log"
UI_DIR = "ui"
UI_FILE = "index.html"

# 前端主题（CSS 变量在 index.html 里定义，值为这里列出的键名）
LIGHT_THEME = "light"
DARK_THEME = "dark"
THEME_CHOICES = [
    ("dark", "深色 · Midnight"),
    ("light", "浅色 · Daylight"),
    ("nord", "深色 · Nord"),
    ("solar", "浅色 · Solarized"),
]

LOG = logging.getLogger("ruku.ui")


# ---------------------------------------------------------------- 纯函数（保持原语义）
def format_judge(j):
    """(可下载, 运行标记, 联机标记, 说明) -> 一行人读文案。"""
    dl, run, online, desc = (list(j) + ["", "", "", ""])[:4]
    return "下载:%s | 运行:%s | 联机:%s | %s" % (
        "可" if dl else "否", run or "-", online or "-", desc or ""
    )


def account_label(acc):
    if not acc:
        return "未登录"
    name = acc.get("account_name") or acc.get("persona_name") or "?"
    return "%s (accountid %s)" % (name, acc.get("accountid", "?"))


def _upsert_block(appid, name, info):
    """普通入库：把 AA.build_block 生成的幂等块覆盖式写入 mygames.lua。"""
    blk = AA.build_block(appid, name=name, info=info)
    lua = P.lua_path()
    txt = V.read_text()
    newtxt = V.strip_game(txt, appid)
    if newtxt and not newtxt.endswith("\n"):
        newtxt += "\n"
    os.makedirs(os.path.dirname(lua), exist_ok=True)
    with open(lua, "w", encoding="utf-8") as f:
        f.write(newtxt + blk)
    return blk


# ---------------------------------------------------------------- 偏好 / 资源定位 / 日志
def _prefs_path():
    return os.path.join(P.writable_dir(), PREF_FILE)


def load_prefs():
    try:
        with open(_prefs_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_prefs(data):
    try:
        with open(_prefs_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _ui_path():
    return os.path.join(P.resource_dir(), UI_DIR, UI_FILE)


def _setup_logging():
    """--windowed 下 stderr 会被丢弃，错误必须落文件（writable_dir 内）。"""
    if LOG.handlers:
        return
    LOG.setLevel(logging.INFO)
    try:
        fh = logging.FileHandler(os.path.join(P.writable_dir(), LOG_FILE), encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOG.addHandler(fh)
    except Exception:
        pass

    def _hook(exc_type, exc, tb):
        LOG.error("未捕获异常", exc_info=(exc_type, exc, tb))

    def _thook(args):
        if args.exc_value is not None:
            LOG.error(
                "线程未捕获异常: %s",
                getattr(args.thread, "name", "?"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

    sys.excepthook = _hook
    try:
        threading.excepthook = _thook
    except Exception:
        pass


FALLBACK_HTML = (
    "<!doctype html><meta charset='utf-8'><body style=\"font-family:'Microsoft YaHei UI';"
    "background:#0f1115;color:#e6e9ef;padding:32px\"><h2>入库中心</h2>"
    "<p>界面资源 %s 缺失，请重新打包或从源码运行。</p></body>" % UI_FILE
)


def _load_html():
    for p in (_ui_path(), os.path.join(os.path.dirname(os.path.abspath(__file__)), UI_DIR, UI_FILE)):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except Exception:
            continue
    return FALLBACK_HTML


# ---------------------------------------------------------------- js_api 桥
class Bridge:
    """pywebview 的 js_api 对象：每个方法返回 {ok, data, error}。

    注意：js_api 的公开属性会被 pywebview 递归扫描并暴露给前端，
    所以窗口句柄等内部状态一律用下划线前缀，避免无限递归。
    """

    def __init__(self):
        prefs = load_prefs()
        theme = prefs.get("theme") or DARK_THEME
        if theme not in dict(THEME_CHOICES):
            theme = DARK_THEME
        self.theme = theme
        self._window = None
        self._accounts = []

    # -- 统一返回
    @staticmethod
    def _ok(data=None):
        return {"ok": True, "data": data, "error": ""}

    def _err(self, exc, prefix):
        LOG.error("%s: %s", prefix, exc, exc_info=True)
        try:
            B.audit("error", prefix, [str(exc)])
        except Exception:
            pass
        return {"ok": False, "data": None, "error": "%s: %s" % (prefix, exc)}

    # -- 数据快照
    def _library(self):
        txt = V.read_text()
        ids = []
        for m in re.finditer(r"--\s*#OSTBLOCK:(\d+)", txt):
            a = int(m.group(1))
            if a not in ids:
                ids.append(a)
        names = G.load_names()
        return [{"appid": a, "name": names.get(str(a), "")} for a in sorted(set(ids))]

    def _locklib(self):
        out = []
        for appid, rec in sorted(V.load_library().items(), key=lambda x: int(x[0])):
            gids = rec.get("locked_gids") or {}
            out.append({
                "appid": str(appid),
                "name": rec.get("name", ""),
                "gid_count": len(gids),
            })
        return out

    def _snapshots(self):
        out = []
        if os.path.isdir(B.SNAPSHOT_ROOT):
            for d in sorted(os.listdir(B.SNAPSHOT_ROOT), reverse=True):
                full = os.path.join(B.SNAPSHOT_ROOT, d)
                if os.path.isfile(os.path.join(full, "manifest.json")):
                    out.append({"dir": full, "name": d})
        return out

    def _account_payload(self):
        accs = P.list_accounts()
        self._accounts = accs
        cur = P.current_account()
        idx = 0
        if cur:
            for i, a in enumerate(accs):
                if a.get("steam64") == cur.get("steam64"):
                    idx = i
                    break
        return {
            "current": account_label(cur),
            "items": [{"label": account_label(a), "accountid": a.get("accountid")} for a in accs],
            "index": idx if accs else -1,
        }

    def _audit_tail(self, n=12):
        if not os.path.isfile(B.AUDIT_PATH):
            return ""
        try:
            with open(B.AUDIT_PATH, encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-n:])
        except Exception:
            return ""

    # -- 启动
    def boot(self):
        try:
            running = P.steam_running()
            return self._ok({
                "title": APP_TITLE,
                "theme": self.theme,
                "themes": [{"key": k, "label": v} for k, v in THEME_CHOICES],
                "account": account_label(P.current_account()),
                "steam_running": running,
                "status": "Steam 运行中" if running else "Steam 未运行",
                "lua_path": P.lua_path(),
                "data_dir": P.writable_dir(),
                "library": self._library(),
                "locklib": self._locklib(),
                "accounts": self._account_payload(),
                "snapshots": self._snapshots(),
                "audit": self._audit_tail(),
            })
        except Exception as e:
            return self._err(e, "启动失败")

    def update_check(self):
        """启动只读自检：有变化才返回报告，否则返回空。"""
        try:
            UG.build_baseline()
            items = UG.check_updates()
            return self._ok({"report": UG.format_report(items) if items else "", "changed": bool(items)})
        except Exception as e:
            return self._err(e, "版本自检失败")

    def set_theme(self, name):
        if name in dict(THEME_CHOICES):
            self.theme = name
            prefs = load_prefs()
            prefs["theme"] = name
            save_prefs(prefs)
            return self._ok(name)
        return {"ok": False, "data": None, "error": "未知主题: %s" % name}

    # -- Tab 1 入库
    def list_library(self):
        try:
            return self._ok(self._library())
        except Exception as e:
            return self._err(e, "读取入库清单失败")

    def search_games(self, query):
        try:
            q = (query or "").strip()
            if not q:
                return self._ok([])
            hits = G.search(q) or []
            return self._ok([{"appid": a, "name": n} for a, n in hits])
        except Exception as e:
            return self._err(e, "搜索失败")

    def add_game(self, arg):
        try:
            arg = (arg or "").strip()
            if not arg:
                return {"ok": False, "data": None, "error": "请输入游戏名或 AppID"}
            appid, name0, err = AA.resolve(arg)
            if err or not appid:
                return {"ok": False, "data": None, "error": err or "解析失败"}
            info = AA.fetch_app_info(appid)
            name = name0 or info.get("name") or str(appid)
            has_key = bool(info.get("depots"))
            if has_key:
                _upsert_block(appid, name, info)
                G.add_name(appid, name)
                B.audit("add", str(appid), [P.lua_path()])
                judge = format_judge(AA.judge(appid, info))
                return self._ok({"appid": appid, "name": name, "has_key": True,
                                 "judge": judge, "library": self._library()})
            judge = format_judge(AA.judge(appid, info))
            return self._ok({"appid": appid, "name": name, "has_key": False, "judge": judge,
                             "message": "key 库无此游戏：可能只是空壳入库，下载不了",
                             "library": self._library()})
        except Exception as e:
            return self._err(e, "入库失败")

    def remove_game(self, appid):
        try:
            a = int(appid)
            txt = V.read_text()
            newtxt = V.strip_game(txt, a)
            with open(P.lua_path(), "w", encoding="utf-8") as f:
                f.write(newtxt)
            B.audit("remove", str(a), [P.lua_path()])
            return self._ok({"appid": a, "library": self._library()})
        except Exception as e:
            return self._err(e, "移除失败")

    def open_lua_dir(self):
        try:
            d = os.path.dirname(P.lua_path())
            os.startfile(d)
            return self._ok(d)
        except Exception as e:
            return self._err(e, "打开目录失败")

    # -- Tab 2 版本锁定
    def list_locklib(self):
        try:
            return self._ok(self._locklib())
        except Exception as e:
            return self._err(e, "读取破解库失败")

    def apply_lock(self, appid):
        try:
            lib = V.load_library()
            rec = lib.get(str(appid)) or lib.get(appid) or {}
            gids = rec.get("locked_gids") or {}
            if not gids:
                return {"ok": False, "data": None, "error": "这条记录没有锁定 GID"}
            info = AA.fetch_app_info(int(appid))
            V.upsert_lock_block(int(appid), rec.get("name", ""), gids, info, note="GUI 应用锁定")
            B.audit("lock", str(appid), [P.lua_path()])
            return self._ok({"appid": appid, "gid_count": len(gids), "name": rec.get("name", ""),
                             "library": self._library()})
        except Exception as e:
            return self._err(e, "锁定失败")

    def import_crackpack(self):
        """先让用户选 zip/lua，取消则选目录；识别 AppID、锁定 GID、暂存补丁。"""
        try:
            path = self._pick_path(dialog="open", title="选破解包(zip/lua)")
            if not path:
                path = self._pick_path(dialog="folder", title="或选破解包目录")
            if not path:
                return self._ok(None)
            if isinstance(path, (list, tuple)):
                path = path[0]
            appid_s = os.path.basename(path).split("_")[0]
            lvas, patch_files = V.find_patch_files(path)
            aid = None
            for lua in lvas:
                m = re.search(r"addappid\s*\(\s*(\d{4,})", lua)
                if m:
                    aid = int(m.group(1))
                    break
            if aid is None and appid_s.isdigit():
                aid = int(appid_s)
            if aid is None:
                return {"ok": False, "data": None, "error": "没从破解包里识别出 AppID，请手动在版本库补记录"}
            gids = {}
            for lua in lvas:
                gids.update(V.extract_gids(lua))
            info = AA.fetch_app_info(aid)
            V.upsert_lock_block(aid, info.get("name", ""), gids, info, note="导入破解包")
            staged = V.stage_patch(aid, patch_files)
            lib = V.load_library()
            lib[str(aid)] = {
                "name": info.get("name", str(aid)),
                "locked_gids": gids,
                "verified": False,
            }
            V.save_library(lib)
            B.audit("import_patch", str(aid), staged[:5])
            return self._ok({"appid": aid, "gid_count": len(gids), "staged": len(staged),
                             "locklib": self._locklib(), "library": self._library()})
        except Exception as e:
            return self._err(e, "导入破解包失败")

    # -- Tab 3 补丁
    def pick_patch(self):
        try:
            p = self._pick_path(dialog="open", title="选补丁包 zip")
            if not p:
                p = self._pick_path(dialog="folder", title="或选补丁目录")
            if isinstance(p, (list, tuple)):
                p = p[0] if p else ""
            return self._ok(p or "")
        except Exception as e:
            return self._err(e, "选择补丁包失败")

    def scan_patch(self, appid, path, game_dir):
        try:
            appid_s = str(appid or "").strip()
            if not appid_s.isdigit() or not path:
                return {"ok": False, "data": None, "error": "填数字 AppID 和补丁包路径"}
            aid = int(appid_s)
            explicit = (game_dir or "").strip() or None
            gd = AP.find_game_dir(aid, explicit)
            items = AP.collect_patch_files(path, os.path.join(P.writable_dir(), "_ap_preview"))
            return self._ok({
                "appid": aid,
                "game_dir": gd or "",
                "items": [{"rel": rel, "src": os.path.basename(src)} for rel, src in items],
            })
        except Exception as e:
            return self._err(e, "扫描失败")

    def apply_patch(self, appid, path, game_dir):
        try:
            aid = int(str(appid).strip())
            items = AP.collect_patch_files(path, os.path.join(P.writable_dir(), "_ap_preview"))
            AP.apply(aid, path, game_dir, dry_run=False)
            B.audit("patch", str(aid), [game_dir, path])
            return self._ok({"appid": aid, "count": len(items), "game_dir": game_dir})
        except Exception as e:
            return self._err(e, "补丁覆盖失败")

    # -- Tab 4 备份与隔离
    def list_accounts(self):
        try:
            return self._ok(self._account_payload())
        except Exception as e:
            return self._err(e, "读取账号失败")

    def backup_now(self, index):
        try:
            acc = None
            i = int(index) if str(index).lstrip("-").isdigit() else -1
            if 0 <= i < len(self._accounts):
                acc = self._accounts[i]
            aid = acc["accountid"] if acc else None
            d = B.snapshot(B.default_targets(aid), label="manual")
            return self._ok({"dir": d, "snapshots": self._snapshots()})
        except Exception as e:
            return self._err(e, "备份失败")

    def health(self):
        try:
            return self._ok(B.health_check())
        except Exception as e:
            return self._err(e, "配置体检失败")

    def list_snapshots(self):
        try:
            return self._ok({"snapshots": self._snapshots(), "audit": self._audit_tail()})
        except Exception as e:
            return self._err(e, "读取快照失败")

    def rollback(self, snap_dir):
        try:
            if P.steam_running():
                return {"ok": False, "data": None,
                        "error": "Steam 正在运行。请完全退出 Steam 后再回滚（回滚会覆盖配置文件）。"}
            if not snap_dir or not os.path.isdir(snap_dir):
                return {"ok": False, "data": None, "error": "快照目录不存在"}
            ok = B.rollback(snap_dir)
            return self._ok({"ok": bool(ok), "dir": snap_dir, "snapshots": self._snapshots()})
        except Exception as e:
            return self._err(e, "回滚失败")

    # -- 文件对话框
    def _pick_path(self, dialog="open", title="选择"):
        if self._window is None or webview is None:
            return ""
        try:
            fd = getattr(webview, "FileDialog", None)
            if dialog == "folder":
                kind = fd.FOLDER if fd is not None else webview.FOLDER_DIALOG
                r = self._window.create_file_dialog(kind, allow_multiple=False)
            else:
                kind = fd.OPEN if fd is not None else webview.OPEN_DIALOG
                r = self._window.create_file_dialog(
                    kind,
                    allow_multiple=False,
                    file_types=("Zip / Lua (*.zip;*.lua)", "所有文件 (*.*)"),
                )
        except Exception as e:
            LOG.warning("文件对话框失败: %s", e)
            return ""
        if not r:
            return ""
        return r[0] if isinstance(r, (list, tuple)) else r

    # -- 主题（前端也可直接改 CSS 变量，这里只做持久化）
    def reload_theme(self):
        return self._ok(self.theme)


# ---------------------------------------------------------------- 启动
def _after_start():
    """start(func) 回调：跑在工作线程，可安全调用窗口 API。

    exe 图标由 spec 的 icon= 嵌入，窗口标题栏会自动采用，这里不再改 native，
    只记录版本号，方便现场排查。
    """
    try:
        LOG.info("界面已启动，版本 %s", _webview_version())
    except Exception as e:
        LOG.warning("启动钩子异常: %s", e)


def _webview_version():
    try:
        from webview import _version

        return getattr(_version, "__version__", "?")
    except Exception:
        return "?"


def main():
    _setup_logging()
    prefs = load_prefs()
    theme = prefs.get("theme") or DARK_THEME
    if theme not in dict(THEME_CHOICES):
        theme = DARK_THEME

    if webview is None:
        _fatal("未安装 pywebview，无法启动界面。\n请在 Python 环境执行: pip install pywebview")
        return

    LOG.info("启动 %s（主题 %s，pywebview %s）", APP_TITLE, theme, _webview_version())

    bridge = Bridge()
    html = _load_html()
    window = webview.create_window(
        APP_TITLE,
        html=html,
        js_api=bridge,
        width=1060,
        height=760,
        min_size=(940, 660),
        background_color="#0b0e14",
        text_select=True,
    )
    bridge._window = window
    webview.start(func=_after_start, debug=False, private_mode=False)


def _fatal(msg):
    """无界面依赖时的兜底提示（不引 tkinter，保持单一 UI 栈）。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, APP_TITLE, 0x10)
    except Exception:
        print(msg, file=sys.stderr)


if __name__ == "__main__":
    main()
