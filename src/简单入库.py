# -*- coding: utf-8 -*-
"""
简单入库程序 —— OpenSteamTool 图形化入库工具（全自动版）
输入游戏名或 AppID → 自动联网拿 depot key + 实时 manifest + DRM 判断 → 写入 mygames.lua。
无需手工补 key、无需每次找人。联网失败自动降级到本地缓存。
"""
import os, re, threading
import tkinter as tk
from tkinter import ttk, messagebox

import auto_adapt as AA
import steam_path as SP

_LUA_PATH = None


def lua_path():
    """惰性获取 mygames.lua 路径；找不到 Steam 时才报错提示。"""
    global _LUA_PATH
    if not _LUA_PATH:
        _LUA_PATH = SP.get_lua_path()
    return _LUA_PATH
MARK_FMT = "-- #OSTBLOCK:{}"
END_MARK = "-- #OSTENDBLOCK"


def strip_game(txt, appid):
    """移除该游戏全部旧痕迹：标记块 + 裸 addappid 行（兜底，幂等）。"""
    txt = re.sub(r"%s\n.*?%s\n" % (re.escape(MARK_FMT.format(appid)), re.escape(END_MARK)),
                 "", txt, flags=re.S)
    txt = re.sub(r"(?:^\s*--[^\n]*\n)?^\s*addappid\(\s*%s\s*[,)].*\n?" % re.escape(str(appid)),
                 "", txt, flags=re.M)
    txt = re.sub(r'^\s*setManifestid\(\s*"?%s"?\s*,.*\n?' % re.escape(str(appid)),
                 "", txt, flags=re.M)
    return txt


def read_text():
    if not os.path.isfile(lua_path()):
        return ""
    with open(lua_path(), "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def upsert(appid, name, info=None):
    """覆盖式入库：清旧 → 用 auto_adapt 生成的完整块写入，保证幂等。"""
    txt = read_text()
    newtxt = strip_game(txt, appid)
    blk = AA.build_block(appid, name or "", info=info,
                         mark_fmt=MARK_FMT, end=END_MARK)
    if newtxt and not newtxt.endswith("\n"):
        newtxt += "\n"
    os.makedirs(os.path.dirname(lua_path()), exist_ok=True)
    with open(lua_path(), "w", encoding="utf-8") as f:
        f.write(newtxt + blk)


def ids_in(txt):
    # 只认标记块里的主游戏，避免把 depot 也算成"已入库游戏"
    ids = set()
    for m in re.finditer(re.escape(MARK_FMT.format("")) + r"(\d+)", txt):
        ids.add(int(m.group(1)))
    if not ids:
        ids = set(int(m) for m in re.findall(r"addappid\(\s*(\d+)", txt))
    return sorted(ids)


class App:
    def __init__(self, root):
        self.root = root
        root.title("简单入库 · OpenSteamTool 全自动")
        root.geometry("560x500")
        root.resizable(False, False)
        self._build()
        self.after_refresh()

    def _build(self):
        frm = ttk.Frame(self.root, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="OpenSteamTool · 全自动入库",
                  font=("Microsoft YaHei", 15, "bold")).pack(anchor="w")
        ttk.Label(frm, text="输入游戏名 / AppID → 自动联网取 key + manifest + DRM 判断",
                  foreground="#555").pack(anchor="w", pady=(2, 10))

        inp = ttk.Frame(frm)
        inp.pack(fill="x")
        self.entry = ttk.Entry(inp, font=("Microsoft YaHei", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.on_add())
        self.btn_add = ttk.Button(inp, text="添加入库", width=10, command=self.on_add)
        self.btn_add.pack(side="left", padx=(8, 0))

        self.status = ttk.Label(frm, text="", foreground="#0a7", wraplength=520, justify="left")
        self.status.pack(anchor="w", pady=(8, 4))

        ttk.Label(frm, text="已入库游戏（主 AppID）：").pack(anchor="w", pady=(8, 2))
        lstfrm = ttk.Frame(frm)
        lstfrm.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(lstfrm, font=("Consolas", 10))
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lstfrm, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        bar = ttk.Frame(frm)
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="刷新", command=self.after_refresh).pack(side="left")
        ttk.Button(bar, text="移除选中", command=self.on_remove).pack(side="left", padx=6)
        ttk.Button(bar, text="刷新Key库(7天)", command=self.on_reload_keys).pack(side="left", padx=6)
        ttk.Button(bar, text="打开配置目录", command=self.open_dir).pack(side="right")

        ttk.Label(frm, text="提示：联网自动取 ManifestHub 全量 depot key（本地缓存 16MB，7 天刷新）。\n"
                            "入库后需完全重启 Steam。EA/Ubisoft/微软等自有账号+反作弊的游戏，key 全自动也联机不了。",
                  foreground="#999", wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))

    def set_status(self, text, ok=True):
        self.status.config(text=text, foreground="#0a7" if ok else "#c33")

    def after_refresh(self):
        self.listbox.delete(0, "end")
        for i in ids_in(read_text()):
            self.listbox.insert("end", str(i))

    def on_add(self):
        raw = self.entry.get().strip()
        if not raw:
            self.set_status("请输入游戏名或 AppID", False)
            return
        self.btn_add.config(state="disabled")
        self.set_status("联网解析中（首次可能需几秒）…")
        threading.Thread(target=self._add_worker, args=(raw,), daemon=True).start()

    def _add_worker(self, raw):
        try:
            aid, name, err = AA.resolve(raw)
            if err or not aid:
                self.root.after(0, lambda: (self.set_status(err or "未解析到 AppID", False),
                                            self.btn_add.config(state="normal")))
                return
            txt = read_text()
            already = bool(re.search(r"-- #OSTBLOCK:%d\b" % aid, txt))
            # 拉取完整适配信息（key + manifest + DRM + 发行商）
            info = AA.fetch_app_info(aid)
            upsert(aid, name, info)
            dl, run, online, desc = AA.judge(aid, info)
            tag = "已刷新" if already else "已入库"
            label = info.get("name") or name or ""
            head = f"{tag} {aid}" + (f" · {label}" if label else "")
            self.root.after(0, lambda: (
                self.set_status(head + "\n" + desc, ok_dl := bool(dl)),
                self.entry.delete(0, "end"),
                self.after_refresh(),
                self.btn_add.config(state="normal"),
            ))
        except Exception as e:
            self.root.after(0, lambda: (self.set_status(f"出错：{type(e).__name__}: {e}", False),
                                        self.btn_add.config(state="normal")))

    def on_remove(self):
        sel = self.listbox.curselection()
        if not sel:
            self.set_status("请先选中一个 AppID", False)
            return
        aid = int(self.listbox.get(sel[0]))
        txt = read_text()
        new = strip_game(txt, aid)
        if new != txt:
            with open(lua_path(), "w", encoding="utf-8") as f:
                f.write(new)
            self.after_refresh()
            self.set_status(f"已移除 {aid}")
        else:
            self.set_status(f"未找到 {aid}", False)

    def on_reload_keys(self):
        self.set_status("正在从 GitHub 刷新全量 key 库（16MB）…")
        def w():
            try:
                db = AA.refresh_master_keys(force=True)
                self.root.after(0, lambda: self.set_status(f"key 库已刷新：{len(db)} 条"))
            except Exception as e:
                self.root.after(0, lambda: self.set_status(f"刷新失败：{e}", False))
        threading.Thread(target=w, daemon=True).start()

    def open_dir(self):
        os.startfile(os.path.dirname(lua_path()))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
