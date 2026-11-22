# -*- coding: utf-8 -*-
"""
addgame_pro.py —— OpenSteamTool 入库增强工具（全自动版）
接入 auto_adapt：输入名字/AppID 自动联网取 depot key + 实时 manifest + DRM 判断。

用法：
  python addgame_pro.py 1145360                     # 单个 AppID
  python addgame_pro.py "Hades" "Hollow Knight"     # 多个游戏名
  python addgame_pro.py --file games.txt            # 从文件批量
  python addgame_pro.py 1091500 --token TOKEN       # 额外带 access token
  python addgame_pro.py --list                      # 查看已入库
  python addgame_pro.py --remove 550                # 移除
  python addgame_pro.py --reload-keys               # 强制刷新全量 key 库
"""
import sys, os, re, argparse
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
    """移除该游戏全部旧痕迹，杜绝孤儿累积。"""
    txt = re.sub(r"%s\n.*?%s\n" % (re.escape(MARK_FMT.format(appid)), re.escape(END_MARK)),
                 "", txt, flags=re.S)
    for a in {str(appid)}:
        txt = re.sub(r"(?:^\s*--[^\n]*\n)?^\s*addappid\(\s*%s\s*[,)].*\n?" % re.escape(a),
                     "", txt, flags=re.M)
        txt = re.sub(r'^\s*setManifestid\(\s*"?%s"?\s*,.*\n?' % re.escape(a),
                     "", txt, flags=re.M)
        txt = re.sub(r'^\s*addtoken\(\s*%s\s*,.*\n?' % re.escape(a),
                     "", txt, flags=re.M)
    return txt


def read_existing():
    if not os.path.isfile(lua_path()):
        return ""
    with open(lua_path(), "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def has_appid(existing, appid):
    return bool(re.search(r"-- #OSTBLOCK:%d\b" % appid, existing)) or \
           bool(re.search(r"addappid\(\s*%d\s*[,)]" % appid, existing))


def upsert(appid, label, info=None, token=None):
    """覆盖式入库，幂等。"""
    txt = read_existing()
    newtxt = strip_game(txt, appid)
    blk = AA.build_block(appid, label or "", info=info,
                         mark_fmt=MARK_FMT, end=END_MARK)
    if token:
        blk = blk.rstrip("\n") + '\naddtoken(%d, "%s")\n' % (appid, token)
    if newtxt and not newtxt.endswith("\n"):
        newtxt += "\n"
    os.makedirs(os.path.dirname(lua_path()), exist_ok=True)
    with open(lua_path(), "w", encoding="utf-8") as f:
        f.write(newtxt + blk)


def cmd_add(args):
    names = []
    for a in args.games:
        if os.path.isfile(a):
            with open(a, "r", encoding="utf-8", errors="replace") as f:
                names += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        else:
            names.append(a)
    added, refreshed, failed = [], [], []
    for n in names:
        aid, label, err = AA.resolve(n)
        if err or not aid:
            failed.append((n, err or "未解析")); continue
        existed = has_appid(read_existing(), aid)
        print(f"[联网] {aid} {label} → 取 depot key + manifest + DRM…")
        info = AA.fetch_app_info(aid)
        upsert(aid, label, info, args.token)
        (refreshed if existed else added).append((aid, info.get("name") or label))
        dl, run, online, desc = AA.judge(aid, info)
        flag = "OK" if dl else "[警告] 下载不了"
        print(f"  → {flag} · {desc}")
    for aid, label in added:
        print(f"[完成] addappid({aid})  -- {label}")
    for aid, label in refreshed:
        print(f"[刷新] AppID {aid} 已存在，已更新 -- {label}")
    for n, why in failed:
        print(f"[失败] {n}: {why}")
    if added or refreshed:
        print(f"\n共 {len(added)+len(refreshed)} 个（新增 {len(added)}，刷新 {len(refreshed)}）。首次请完全重启 Steam。")


def cmd_list(args):
    existing = read_existing()
    ids = set(int(m.group(1)) for m in re.finditer(re.escape(MARK_FMT.format("")) + r"(\d+)", existing))
    if not ids:
        ids = set(int(m) for m in re.findall(r"addappid\(\s*(\d+)", existing))
    print(f"当前入库 {len(ids)} 个主游戏 AppID ({lua_path()}):")
    for i in sorted(ids):
        print(f"  {i}")


def cmd_remove(args):
    existing = read_existing()
    aid = args.remove
    new = strip_game(existing, aid)
    if new == existing:
        print(f"[提示] 未找到 addappid({aid})"); return
    with open(lua_path(), "w", encoding="utf-8") as f:
        f.write(new)
    print(f"[完成] 已移除 AppID {aid} 及其全部 depot/manifest 项。重启 Steam 生效。")


def main():
    p = argparse.ArgumentParser(description="OpenSteamTool 全自动入库工具")
    p.add_argument("games", nargs="*", help="游戏名 / AppID / 商店链接 / 文本文件")
    p.add_argument("--token", help="access token")
    p.add_argument("--file", dest="file_arg", help="从文件批量读取")
    p.add_argument("--list", action="store_true", help="列出已入库主游戏")
    p.add_argument("--remove", type=int, metavar="APPID", help="移除指定 AppID")
    p.add_argument("--reload-keys", action="store_true", help="强制刷新全量 depot key 库")
    args = p.parse_args()

    if args.reload_keys:
        db = AA.refresh_master_keys(force=True)
        print(f"[完成] 全量 key 库已刷新：{len(db)} 条"); return
    if args.file_arg:
        args.games = [args.file_arg] + list(args.games)
    if args.list:
        cmd_list(args); return
    if args.remove:
        cmd_remove(args); return
    if not args.games:
        p.print_help(); return
    cmd_add(args)


if __name__ == "__main__":
    main()
