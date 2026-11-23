# -*- coding: utf-8 -*-
"""入库中心 v2 —— 统一 4-tab GUI。所有重活走后台线程，after() 回主线程更 UI。"""
import os
import re
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import paths as P
import auto_adapt as AA
import version_lock as V
import apply_patch as AP
import game_index as G
import backup as B
import update_guard as UG

MARK_FMT = "-- #OSTBLOCK:{}"
END_MARK = "-- #OSTENDBLOCK"


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
    # 用 version_lock 的 strip_game 逻辑清旧块，避免和锁定块共用标记
    newtxt = V.strip_game(txt, appid)
    if newtxt and not newtxt.endswith("\n"):
        newtxt += "\n"
    os.makedirs(os.path.dirname(lua), exist_ok=True)
    with open(lua, "w", encoding="utf-8") as f:
        f.write(newtxt + blk)
    return blk


class App:
    def __init__(self, root):
        self.root = root
        root.title("入库中心 · OpenSteamTool 全自动 v2")
        root.geometry("880x640")
        self._build_top()
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tab_import = ttk.Frame(self.nb)
        self.tab_lock = ttk.Frame(self.nb)
        self.tab_patch = ttk.Frame(self.nb)
        self.tab_backup = ttk.Frame(self.nb)
        self.nb.add(self.tab_import, text="入库")
        self.nb.add(self.tab_lock, text="版本锁定")
        self.nb.add(self.tab_patch, text="补丁")
        self.nb.add(self.tab_backup, text="备份与隔离")
        self._build_import()
        self._build_lock()
        self._build_patch()
        self._build_backup()
        self._refresh_import_list()
        self._startup_update_check()

    # ---------------- 顶部状态条
    def _build_top(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=8)
        self.lbl_status = ttk.Label(bar, text="", foreground="#0a6")
        self.lbl_status.pack(side="left")
        acc = P.current_account()
        self.lbl_acc = ttk.Label(bar, text="账号: " + account_label(acc))
        self.lbl_acc.pack(side="right")
        running = P.steam_running()
        self.lbl_status.config(
            text=("Steam 运行中" if running else "Steam 未运行"),
            foreground=("#0a6" if running else "#a60"),
        )

    def _bg(self, fn, done=None, err_prefix="操作失败"):
        """后台执行 fn()，完成后 done(result) 回主线程。"""
        def run():
            try:
                res = fn()
            except Exception as e:
                self.root.after(0, lambda e=e: messagebox.showerror("错误", "%s: %s" % (err_prefix, e)))
                B.audit("error", err_prefix, [str(e)])
                return
            if done:
                self.root.after(0, lambda: done(res))
        threading.Thread(target=run, daemon=True).start()

    # ---------------- Tab 1: 入库
    def _build_import(self):
        f = self.tab_import
        top = ttk.Frame(f)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="游戏名 / AppID / 商店链接:").pack(side="left")
        self.ent_game = ttk.Entry(top, width=42)
        self.ent_game.pack(side="left", padx=6)
        self.ent_game.bind("<Return>", lambda e: self.on_add())
        ttk.Button(top, text="搜索名字", command=self.on_search).pack(side="left", padx=3)
        ttk.Button(top, text="入库", command=self.on_add).pack(side="left", padx=3)
        self.lst_hits = tk.Listbox(top, height=4, width=40)
        self.lst_hits.pack(side="left", padx=6)
        self.lst_hits.bind("<Double-Button-1>", self.on_pick_hit)

        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, padx=10)
        ttk.Label(mid, text="已入库游戏:").pack(anchor="w")
        self.lst_lib = tk.Listbox(mid)
        self.lst_lib.pack(fill="both", expand=True, side="left")
        btns = ttk.Frame(mid)
        btns.pack(side="left", fill="y", padx=6)
        ttk.Button(btns, text="刷新", command=self._refresh_import_list).pack(fill="x", pady=2)
        ttk.Button(btns, text="移除选中", command=self.on_remove).pack(fill="x", pady=2)
        ttk.Button(btns, text="打开配置目录", command=self.on_open_dir).pack(fill="x", pady=2)

        self.lbl_import_status = ttk.Label(f, text="", wraplength=840, foreground="#444")
        self.lbl_import_status.pack(fill="x", padx=10, pady=8)

    def _refresh_import_list(self):
        self.lst_lib.delete(0, "end")
        txt = V.read_text()
        ids = []
        for m in re.finditer(r"--\s*#OSTBLOCK:(\d+)", txt):
            a = int(m.group(1))
            if a not in ids:
                ids.append(a)
        names = G.load_names()
        for a in sorted(set(ids)):
            self.lst_lib.insert("end", "%s  %s" % (a, names.get(str(a), "")))

    def on_search(self):
        q = self.ent_game.get().strip()
        if not q:
            return
        self.lbl_import_status.config(text="搜索中…")
        self._bg(lambda: G.search(q), self._show_hits, "搜索失败")

    def _show_hits(self, hits):
        self.lst_hits.delete(0, "end")
        self._hits = hits or []
        for appid, name in self._hits:
            self.lst_hits.insert("end", "%s  %s" % (appid, name))
        self.lbl_import_status.config(text=("找到 %d 个，双击选用" % len(self._hits)) if self._hits else "本地+联网都没找到，可直接输数字 AppID")

    def on_pick_hit(self, event):
        sel = self.lst_hits.curselection()
        if not sel:
            return
        appid, name = self._hits[sel[0]]
        self.ent_game.delete(0, "end")
        self.ent_game.insert(0, str(appid))

    def on_add(self):
        arg = self.ent_game.get().strip()
        if not arg:
            messagebox.showwarning("提示", "请输入游戏名或 AppID")
            return
        self.lbl_import_status.config(text="联网解析中…（首次需查 depot/GID）")

        def work():
            appid, name0, err = AA.resolve(arg)
            if err or not appid:
                return None, err or "解析失败"
            info = AA.fetch_app_info(appid)
            name = name0 or info.get("name") or str(appid)
            if not info.get("depots"):
                return (appid, name, info, False), "key 库无此游戏：可能只是空壳入库，下载不了"
            _upsert_block(appid, name, info)
            G.add_name(appid, name)
            B.audit("add", str(appid), [P.lua_path()])
            jd = AA.judge(appid, info)
            return (appid, name, info, True), format_judge(jd)

        def done(res):
            payload, msg = res
            if payload is None:
                self.lbl_import_status.config(text="失败: " + msg, foreground="#b00")
                return
            appid, name, info, has_key = payload
            color = "#b00" if not has_key else "#060"
            self.lbl_import_status.config(text="已入库 %s %s | 仅本地判断: %s" % (appid, name, msg), foreground=color)
            self._refresh_import_list()

        self._bg(work, done, "入库失败")

    def on_remove(self):
        sel = self.lst_lib.curselection()
        if not sel:
            return
        appid = int(self.lst_lib.get(sel[0]).split()[0])
        if not messagebox.askyesno("确认", "从入库清单移除 AppID %s？" % appid):
            return
        txt = V.read_text()
        newtxt = V.strip_game(txt, appid)
        with open(P.lua_path(), "w", encoding="utf-8") as f:
            f.write(newtxt)
        B.audit("remove", str(appid), [P.lua_path()])
        self._refresh_import_list()
        self.lbl_import_status.config(text="已移除 %s" % appid, foreground="#060")

    def on_open_dir(self):
        d = os.path.dirname(P.lua_path())
        try:
            os.startfile(d)
        except Exception as e:
            messagebox.showerror("错误", str(e))

    # ---------------- Tab 2: 版本锁定
    def _build_lock(self):
        f = self.tab_lock
        ttk.Label(f, text="D 加密游戏：锁定历史版本 GID → 下载后可打破解补丁").pack(anchor="w", padx=10, pady=(10, 4))
        self.lst_lib_lock = tk.Listbox(f, height=8)
        self.lst_lib_lock.pack(fill="x", padx=10)
        btns = ttk.Frame(f)
        btns.pack(fill="x", padx=10, pady=6)
        ttk.Button(btns, text="刷新破解库", command=self._refresh_lock_list).pack(side="left", padx=3)
        ttk.Button(btns, text="应用锁定到入库清单", command=self.on_lock_apply).pack(side="left", padx=3)
        ttk.Button(btns, text="导入破解包(zip/目录/lua)", command=self.on_lock_import).pack(side="left", padx=3)
        self.lbl_update_warn = ttk.Label(f, text="", wraplength=840, foreground="#b00", justify="left")
        self.lbl_update_warn.pack(fill="x", padx=10)
        guide = ("固定指引：①完全关闭 Steam  ②删除 <Steam>/appcache/appinfo.vdf  "
                 "③冷启动 Steam  ④核对 content_log 的 Downloading GID 是锁定值  "
                 "⑤下载完把暂存补丁覆盖进游戏目录再启动")
        ttk.Label(f, text=guide, wraplength=840, foreground="#444", justify="left").pack(fill="x", padx=10, pady=8)
        self.lbl_lock_status = ttk.Label(f, text="", wraplength=840, foreground="#444")
        self.lbl_lock_status.pack(fill="x", padx=10)
        self._refresh_lock_list()

    def _startup_update_check(self):
        """后台跑一次只读版本自检；有变化才回主线程告警并弹窗。"""
        self._bg(lambda: (UG.build_baseline(), UG.check_updates()),
                 self._show_update_warn, "版本自检失败")

    def _show_update_warn(self, res):
        items = res[1]
        if items:
            text = UG.format_report(items)
            self.lbl_update_warn.config(text=text)
            messagebox.showwarning("本体版本变化", text)
        else:
            self.lbl_update_warn.config(text="（启动自检完成，已锁定游戏版本正常）")

    def _refresh_lock_list(self):
        self.lst_lib_lock.delete(0, "end")
        lib = V.load_library()
        for appid, rec in sorted(lib.items(), key=lambda x: int(x[0])):
            gids = rec.get("locked_gids") or {}
            self.lst_lib_lock.insert("end", "%s  %s  (%d 个锁定 GID)" % (appid, rec.get("name", ""), len(gids)))
        self._lock_lib = lib

    def on_lock_apply(self):
        sel = self.lst_lib_lock.curselection()
        if not sel:
            messagebox.showwarning("提示", "先在破解库里选中一个游戏")
            return
        appid = self.lst_lib_lock.get(sel[0]).split()[0]
        rec = self._lock_lib.get(appid) or self._lock_lib.get(int(appid)) or {}
        gids = rec.get("locked_gids") or {}
        if not gids:
            messagebox.showwarning("提示", "这条记录没有锁定 GID")
            return
        self.lbl_lock_status.config(text="解析中…")

        def work():
            info = AA.fetch_app_info(int(appid))
            V.upsert_lock_block(int(appid), rec.get("name", ""), gids, info, note="GUI 应用锁定")
            B.audit("lock", appid, [P.lua_path()])
            return "已锁定 %s 的 %d 个 GID（%s）" % (appid, len(gids), rec.get("name", ""))

        self._bg(work, lambda m: self.lbl_lock_status.config(text="仅本地判断: " + m, foreground="#060"), "锁定失败")

    def on_lock_import(self):
        path = filedialog.askopenfilename(title="选破解包(zip/lua)") or filedialog.askdirectory(title="或选破解包目录")
        if not path:
            return
        self.lbl_lock_status.config(text="解析破解包中…")

        def work():
            appid_s = os.path.basename(path).split("_")[0]
            # 优先从 lua 文本里找 addappid 的 appid
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
                return None
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
            return aid, len(gids), len(staged)

        def done(res):
            if not res:
                self.lbl_lock_status.config(text="没从破解包里识别出 AppID，请手动在版本库补记录", foreground="#b00")
                return
            aid, ng, nf = res
            self.lbl_lock_status.config(text="已导入 %s：%d 个 GID 锁定 + %d 个补丁文件暂存" % (aid, ng, nf), foreground="#060")
            self._refresh_lock_list()

        self._bg(work, done, "导入破解包失败")

    # ---------------- Tab 3: 补丁
    def _build_patch(self):
        f = self.tab_patch
        top = ttk.Frame(f)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="AppID:").pack(side="left")
        self.ent_patch_appid = ttk.Entry(top, width=12)
        self.ent_patch_appid.insert(0, "3489700")
        self.ent_patch_appid.pack(side="left", padx=4)
        ttk.Label(top, text="补丁包:").pack(side="left", padx=(12, 2))
        self.ent_patch_path = ttk.Entry(top, width=52)
        self.ent_patch_path.pack(side="left", padx=4)
        ttk.Button(top, text="浏览…", command=self.on_patch_browse).pack(side="left")
        row2 = ttk.Frame(f)
        row2.pack(fill="x", padx=10)
        ttk.Button(row2, text="扫描预览(dry-run)", command=lambda: self.on_patch_apply(dry=True)).pack(side="left", padx=3)
        ttk.Button(row2, text="确认覆盖", command=lambda: self.on_patch_apply(dry=False)).pack(side="left", padx=3)
        ttk.Label(row2, text="游戏目录（留空自动查）:").pack(side="left", padx=(12, 2))
        self.ent_game_dir = ttk.Entry(top, width=30)
        self.lst_patch = tk.Listbox(f, height=14)
        self.lst_patch.pack(fill="both", expand=True, padx=10, pady=8)
        self.lbl_patch_status = ttk.Label(f, text="", wraplength=840, foreground="#444")
        self.lbl_patch_status.pack(fill="x", padx=10)
        # 游戏目录输入框放在 row2 下端
        self.ent_game_dir = ttk.Entry(row2, width=34)
        self.ent_game_dir.pack(side="left", padx=4)

    def on_patch_browse(self):
        p = filedialog.askopenfilename(title="选补丁 zip") or filedialog.askdirectory(title="或选补丁目录")
        if p:
            self.ent_patch_path.delete(0, "end")
            self.ent_patch_path.insert(0, p)

    def on_patch_apply(self, dry=True):
        appid_s = self.ent_patch_appid.get().strip()
        path = self.ent_patch_path.get().strip()
        if not appid_s.isdigit() or not path:
            messagebox.showwarning("提示", "填数字 AppID 和补丁包路径")
            return
        appid = int(appid_s)
        explicit = self.ent_game_dir.get().strip() or None
        self.lbl_patch_status.config(text="扫描中…")
        self._bg(
            lambda: (AP.find_game_dir(appid, explicit), path),
            lambda r: self._patch_do(r, appid, dry),
            "扫描失败",
        )

    def _patch_do(self, res, appid, dry):
        game_dir, path = res
        items = AP.collect_patch_files(path, os.path.join(P.writable_dir(), "_ap_preview"))
        self.lst_patch.delete(0, "end")
        for rel, src in items:
            self.lst_patch.insert("end", "%s  <-  %s" % (rel, os.path.basename(src)))
        if not game_dir:
            self.lbl_patch_status.config(text="没找到游戏目录（游戏可能还没下完），填左侧路径", foreground="#b00")
            return
        if dry:
            self.lbl_patch_status.config(text="预览：%d 个文件将覆盖到 %s（未实际写入）" % (len(items), game_dir), foreground="#060")
            return
        if not messagebox.askyesno("确认覆盖", "把 %d 个文件覆盖进 %s？原文件会备份到游戏目录 _patch_backup" % (len(items), game_dir)):
            return
        AP.apply(appid, path, game_dir, dry_run=False)
        B.audit("patch", str(appid), [game_dir, path])
        self.lbl_patch_status.config(text="补丁已覆盖，原文件备份在游戏目录 _patch_backup", foreground="#060")

    # ---------------- Tab 4: 备份与隔离
    def _build_backup(self):
        f = self.tab_backup
        ttk.Label(f, text="账号（当前自动识别，可切换）:", wraplength=840).pack(anchor="w", padx=10, pady=(10, 2))
        self.cmb_account = ttk.Combobox(f, state="readonly", width=56)
        self.cmb_account.pack(fill="x", padx=10)
        accs = P.list_accounts()
        self._accounts = accs
        cur = P.current_account()
        self.cmb_account["values"] = [account_label(a) for a in accs] or ["<无账号>"]
        idx = 0
        if cur:
            for i, a in enumerate(accs):
                if a["steam64"] == cur["steam64"]:
                    idx = i
                    break
        self.cmb_account.current(idx if accs else 0)

        row = ttk.Frame(f)
        row.pack(fill="x", padx=10, pady=8)
        ttk.Button(row, text="立即备份所选账号配置", command=self.on_backup).pack(side="left", padx=3)
        ttk.Button(row, text="配置体检", command=self.on_health).pack(side="left", padx=3)
        ttk.Button(row, text="刷新快照列表", command=self._refresh_snaps).pack(side="left", padx=3)
        ttk.Label(row, text="回滚前会强制检查 Steam 必须已退出", foreground="#a60").pack(side="left", padx=10)

        ttk.Label(f, text="快照:").pack(anchor="w", padx=10)
        self.lst_snaps = tk.Listbox(f, height=6)
        self.lst_snaps.pack(fill="x", padx=10)
        ttk.Button(f, text="回滚到选中快照", command=self.on_rollback).pack(anchor="w", padx=10, pady=6)
        self.txt_report = tk.Text(f, height=10)
        self.txt_report.pack(fill="both", expand=True, padx=10, pady=6)
        ttk.Label(f, text="提示：改不了“来自家庭库”显示 / 正版联机——那是 Steam 服务器判定，本地工具只做快照与回滚。",
                  wraplength=840, foreground="#a60").pack(fill="x", padx=10, pady=(0, 8))
        self._refresh_snaps()

    def _sel_account(self):
        i = self.cmb_account.current()
        if 0 <= i < len(self._accounts):
            return self._accounts[i]
        return None

    def _refresh_snaps(self):
        self.lst_snaps.delete(0, "end")
        self._snaps = []
        if os.path.isdir(B.SNAPSHOT_ROOT):
            for d in sorted(os.listdir(B.SNAPSHOT_ROOT)):
                full = os.path.join(B.SNAPSHOT_ROOT, d)
                if os.path.isfile(os.path.join(full, "manifest.json")):
                    self._snaps.append(full)
                    self.lst_snaps.insert("end", d)
        self.txt_report.delete("1.0", "end")
        if os.path.isfile(B.AUDIT_PATH):
            lines = open(B.AUDIT_PATH, encoding="utf-8", errors="replace").readlines()[-12:]
            self.txt_report.insert("end", "最近审计:\n" + "".join(lines))

    def on_backup(self):
        acc = self._sel_account()
        aid = acc["accountid"] if acc else None
        d = B.snapshot(B.default_targets(aid), label="manual")
        self.txt_report.insert("end", "已备份到: %s\n" % d)
        self._refresh_snaps()

    def on_health(self):
        h = B.health_check()
        self.txt_report.delete("1.0", "end")
        self.txt_report.insert("end", "配置体检（只读）:\n" + json.dumps(h, ensure_ascii=False, indent=2) + "\n")

    def on_rollback(self):
        sel = self.lst_snaps.curselection()
        if not sel:
            messagebox.showwarning("提示", "先选一个快照")
            return
        d = self._snaps[sel[0]]
        if P.steam_running():
            messagebox.showerror("无法回滚", "Steam 正在运行。请完全退出 Steam 后再回滚（回滚会覆盖配置文件）。")
            return
        if not messagebox.askyesno("确认回滚", "把配置回滚到 %s？当前状态会先自动打一份快照。" % os.path.basename(d)):
            return
        ok = B.rollback(d)
        self.txt_report.insert("end", ("回滚成功: " if ok else "回滚失败(校验未过): ") + d + "\n")
        if ok:
            messagebox.showinfo("完成", "回滚成功。现在可以启动 Steam。")
        self._refresh_snaps()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
