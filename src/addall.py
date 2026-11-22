#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本机所有已安装 Steam 游戏的 AppID 一次性写入 mygames.lua（addappid）。
用法: python addall.py --list | python addall.py --apply
"""
import os
import re
import sys
import glob
import steam_path as SP

STEAM_DIR = SP.find_steam_dir() or r"C:\Program Files (x86)\Steam"
LUA_PATH = os.path.join(STEAM_DIR, "config", "stplug-in", "mygames.lua")
LIBFOLDERS = os.path.join(STEAM_DIR, "steamapps", "libraryfolders.vdf")

# 日志里出现过、但可能未安装的 AppID，也一并纳入
EXTRA_IDS = [1426210, 2507950, 3527290, 4001890, 431960, 824270]


def library_paths():
    paths = [STEAM_DIR]
    try:
        with open(LIBFOLDERS, "r", encoding="utf-8-sig", errors="ignore") as f:
            txt = f.read()
        for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
            p = m.group(1).replace("\\\\", "\\")
            if os.path.isdir(p):
                paths.append(p)
    except Exception as e:
        print(f"[warn] 读 libraryfolders.vdf 失败: {e}")
    # 去重保序
    seen = set()
    out = []
    for p in paths:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def installed_games():
    games = {}  # appid(int) -> name
    for root in library_paths():
        sa = os.path.join(root, "steamapps")
        for acf in glob.glob(os.path.join(sa, "appmanifest_*.acf")):
            m = re.search(r"appmanifest_(\d+)\.acf$", acf)
            if not m:
                continue
            appid = int(m.group(1))
            name = ""
            try:
                with open(acf, "r", encoding="utf-8-sig", errors="ignore") as f:
                    t = f.read()
                nm = re.search(r'"name"\s+"([^"]+)"', t)
                if nm:
                    name = nm.group(1)
            except Exception:
                pass
            games.setdefault(appid, name)
    return games


def existing_ids():
    ids = set()
    if os.path.isfile(LUA_PATH):
        with open(LUA_PATH, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                for m in re.finditer(r"addappid\(\s*(\d+)", line):
                    ids.add(int(m.group(1)))
    return ids


def main():
    games = installed_games()
    for i in EXTRA_IDS:
        games.setdefault(i, "(日志中出现，未在本地库找到)")
    have = existing_ids()

    print(f"[i] Steam 库目录: {library_paths()}")
    print(f"[i] 已安装/待配游戏 {len(games)} 个，mygames.lua 已配 {len(have)} 个\n")
    for aid in sorted(games):
        mark = "已有" if aid in have else "待加"
        print(f"  [{mark}] {aid:>8}  {games[aid]}")

    if "--apply" not in sys.argv:
        print("\n[提示] 加 --apply 参数正式写入 mygames.lua")
        return

    new = sorted(aid for aid in games if aid not in have)
    if not new:
        print("\n[完成] 没有新增，mygames.lua 已覆盖全部。")
        return

    # 全自动 + 幂等：复用 addgame_pro.upsert（内部走 auto_adapt 取 key/manifest/DRM）
    import auto_adapt as AA
    import addgame_pro as AP
    print(f"\n[联网] 逐个拉取 depot key + manifest（{len(new)} 个，首次稍慢）…")
    added = []
    for aid in new:
        name = games.get(aid, "")
        try:
            info = AA.fetch_app_info(aid)
            AP.upsert(aid, name, info)
            dl = bool(info.get("depots"))
            added.append(aid)
            print(f"  [{'可下载' if dl else '仅图标'}] {aid}  {info.get('name') or name}")
        except Exception as e:
            print(f"  [失败] {aid} {name}: {type(e).__name__}")
    print(f"\n[完成] 已全自动入库 {len(added)} 个 AppID（幂等块，不含孤儿行）到 {LUA_PATH}")
    print("\n[下一步] 完全退出并重启 Steam 生效。")


if __name__ == "__main__":
    main()
