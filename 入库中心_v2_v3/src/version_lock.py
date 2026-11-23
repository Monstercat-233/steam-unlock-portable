# -*- coding: utf-8 -*-
"""
version_lock.py —— D 加密游戏「锁定历史版本 + 破解补丁」助手

对应目标的三档策略：
  1. 正常单机直下          → 走 简单入库.exe / auto_adapt（本工具不重复造轮子）
  2. D 加密自动找前人破解  → 查本地破解库 crack_library.json，命中即锁定历史 GID
  3. 实在不行              → 用户自己下载破解包，用 import_patch 导入，自动提 GID + 暂存补丁

为什么历史 GID 不做纯联网爬：
  实测(2026-11-22) steamdb.info/depot/.../manifests/ 返回 403；
  github.com/pjy612/SteamManifestCache/discussions/... 握手超时；
  api.steamcmd.net 只有实时 GID。
  所以最可靠的来源就是用户手里破解包自带的锁定版 lua（老 GID 就在里面）。

用法：
  python version_lock.py 3489700                 # 查该 D 加密游戏该怎么过（查库/指路）
  python version_lock.py 3489700 --import <路径>  # 导入破解包(zip/目录/lua)，自动锁定历史 GID
  python version_lock.py 3489700 --list-lib       # 看破解库里都有哪些游戏
  python version_lock.py --add-lib 4115450 "游戏名" "破解说明" "来源URL"  # 手动补一条库记录
  python version_lock.py 3489700 --lock 3489701=2747626496734343426 ...   # 直接给定 GID 锁定
"""
import os, re, sys, json, shutil, zipfile, argparse
import auto_adapt as AA
import paths as P

HERE = P.resource_dir()
LUA_PATH = P.lua_path()
_wl = os.path.join(P.writable_dir(), "crack_library.json")
_rl = os.path.join(P.resource_dir(), "crack_library.json")
LIB_PATH = _wl if os.path.isfile(_wl) else _rl                   # 优先 exe 旁，可独立更新
PATCH_STORE = os.path.join(P.writable_dir(), "patches")          # 导入的破解包暂存
MARK_FMT = "-- #OSTBLOCK:{}"
END_MARK = "-- #OSTENDBLOCK"
GID_RE = re.compile(r'setManifestid\s*\(\s*"?(\d+)"?\s*,\s*"(\d+)"')
# auto_adapt 的 drm 字段大面积为空（steamcmd.net 数据源限制），用人工核实过的名单兜底
KNOWN_DENUVO = {
    "3489700": "剑星 Stellar Blade",
    "4115450": "影之刃零 Phantom Blade Zero",
    "2358720": "黑神话悟空 Black Myth: Wukong",
}


# ---------------------------------------------------------------- 破解库
def load_library():
    if os.path.isfile(LIB_PATH):
        try:
            return json.load(open(LIB_PATH, "r", encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_library(lib):
    with open(LIB_PATH, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- lua 工具
def read_text():
    if not os.path.isfile(LUA_PATH):
        return ""
    return open(LUA_PATH, "r", encoding="utf-8", errors="replace").read()


def strip_game(txt, appid):
    txt = re.sub(r"%s\n.*?%s\n" % (re.escape(MARK_FMT.format(appid)), re.escape(END_MARK)),
                 "", txt, flags=re.S)
    txt = re.sub(r"(?:^\s*--[^\n]*\n)?^\s*addappid\(\s*%s\s*[,)].*\n?" % re.escape(str(appid)),
                 "", txt, flags=re.M)
    txt = re.sub(r'^\s*setManifestid\(\s*"?%s"?\s*,.*\n?' % re.escape(str(appid)),
                 "", txt, flags=re.M)
    return txt


def extract_gids(text):
    """从 lua 文本提取 {depot_id: gid}，均为字符串。"""
    return {d: g for d, g in GID_RE.findall(text or "")}


def upsert_lock_block(appid, name, locked_gids, info=None, note=""):
    """覆盖式写入锁定块：key 用全量库，GID 用传入的历史版本。数字写法。"""
    info = info or AA.fetch_app_info(appid)
    depots = info.get("depots") or {}
    keys = AA.get_key_db()
    label = name or info.get("name") or str(appid)
    lines = [MARK_FMT.format(appid)]
    lines.append("-- %s  [版本锁定%s]" % (label, ("：" + note) if note else ""))
    if str(appid) in depots:
        lines.append('addappid(%d, 1, "%s")' % (appid, depots[str(appid)]))
    else:
        lines.append("addappid(%d)" % appid)
    for did, k in depots.items():
        if str(did) != str(appid):
            lines.append('addappid(%s, 1, "%s")' % (did, k))
    # 锁定 GID：setManifestid 第一参数必须数字，字符串会被静默忽略
    for did, gid in locked_gids.items():
        if str(did) not in depots:            # 老版本 depot 若当前库无 key，至少补裸 addappid
            k = keys.get(str(did))
            if k and re.fullmatch(r"[0-9a-fA-F]{64}", k or ""):
                lines.append('addappid(%s, 1, "%s")' % (did, k.lower()))
            else:
                lines.append("addappid(%s)" % did)
        lines.append('setManifestid(%s, "%s")' % (did, gid))
    lines.append(END_MARK)
    blk = "\n".join(lines) + "\n"

    txt = read_text()
    newtxt = strip_game(txt, appid)
    if newtxt and not newtxt.endswith("\n"):
        newtxt += "\n"
    os.makedirs(os.path.dirname(LUA_PATH), exist_ok=True)
    with open(LUA_PATH, "w", encoding="utf-8") as f:
        f.write(newtxt + blk)
    return blk


# ---------------------------------------------------------------- 破解包解析
def find_patch_files(path):
    """递归找 zip/目录里的 .lua 和补丁可执行/dll，返回 (lua文本列表, 补丁文件绝对路径列表)。"""
    lvas, patch_files = [], []

    def scan_dir(root):
        for dp, _dn, fns in os.walk(root):
            for fn in fns:
                p = os.path.join(dp, fn)
                if fn.lower().endswith(".lua"):
                    try:
                        lvas.append(open(p, "r", encoding="utf-8", errors="replace").read())
                    except Exception:
                        pass
                elif fn.lower().endswith((".exe", ".dll", ".ini")):
                    patch_files.append(p)

    if os.path.isdir(path):
        scan_dir(path)
    elif os.path.isfile(path) and path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            tmp = os.path.join(HERE, "_vl_unzip_tmp")
            os.makedirs(tmp, exist_ok=True)
            for n in z.namelist():
                if n.endswith("/"):
                    continue
                try:
                    data = z.read(n)
                except Exception:
                    continue
                if n.lower().endswith(".lua"):
                    lvas.append(data.decode("utf-8", "replace"))
                elif n.lower().endswith((".exe", ".dll", ".ini")):
                    dst = os.path.join(tmp, os.path.basename(n))
                    with open(dst, "wb") as f:
                        f.write(data)
                    patch_files.append(dst)
    elif os.path.isfile(path) and path.lower().endswith(".lua"):
        lvas.append(open(path, "r", encoding="utf-8", errors="replace").read())
    return lvas, patch_files


def stage_patch(appid, patch_files):
    """把破解文件按原相对结构复制到 patches/<appid>/，供用户覆盖。"""
    dst_root = os.path.join(PATCH_STORE, str(appid))
    os.makedirs(dst_root, exist_ok=True)
    copied = []
    for p in patch_files:
        # 保留 Steamworks / Binaries 等尾部三级目录结构
        parts = p.replace("\\", "/").split("/")
        rel = "/".join(parts[-4:])
        dst = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
        copied.append(dst)
    return copied


# ---------------------------------------------------------------- 主流程
def plan(appid):
    """检测 D 加密 → 查库 → 给出三档路线。"""
    aid, name, err = AA.resolve(str(appid))
    if err or not aid:
        print("解析失败:", err)
        return
    info = AA.fetch_app_info(aid)
    drm_txt = (info.get("drm") or "").lower()
    is_denuvo = ("denuvo" in drm_txt) or (str(aid) in KNOWN_DENUVO)
    print("=" * 64)
    print("游戏:", info.get("name") or name, "(AppID %d)" % aid)
    print("DRM :", repr(info.get("drm")) or "(空)")
    if str(aid) in KNOWN_DENUVO and "denuvo" not in drm_txt:
        print("       [人工核实名单] D 加密:", KNOWN_DENUVO[str(aid)])
    print("下载:", ("OK (%d depot)" % len(info["depots"])) if info.get("depots") else "无 key")
    print("Denuvo:", "是" if is_denuvo else "否")
    if not is_denuvo:
        print("路线: 【正常直下】无需锁定，直接用 简单入库.exe 入库即可。")
        print("=" * 64)
        return
    lib = load_library().get(str(aid))
    if lib and lib.get("locked_gids"):
        print("路线: 【命中破解库】有前人破解 + 锁定版 GID，可一键锁定。")
        print("  破解:", lib.get("crack"))
        print("  来源:", lib.get("source"))
        print("  版本:", lib.get("version"))
        print("  锁 GID:", lib["locked_gids"])
        print("  执行: python version_lock.py %d --lock %s" % (
            aid, " ".join("%s=%s" % kv for kv in lib["locked_gids"].items())))
    elif lib:
        print("路线: 【库中有破解但缺锁定 GID】")
        print("  破解:", lib.get("crack"))
        print("  来源:", lib.get("source"))
        print("  请从来源下载破解包，然后: python version_lock.py %d --import <破解包.zip或目录>" % aid)
    else:
        print("路线: 【破解库未收录】需你自己下载破解包（推荐 SteamManifestCache Discussions / 3a.lol / NGA / 游侠补丁）")
        print("  拿到包后: python version_lock.py %d --import <破解包.zip或目录>" % aid)
        print("  或手动: python version_lock.py %d --lock <depotid=gid> [<depotid=gid> ...]" % aid)
    print("=" * 64)


def do_lock(appid, pairs, note="破解包锁定版"):
    aid, name, err = AA.resolve(str(appid))
    if err or not aid:
        print("解析失败:", err)
        return
    locked = {}
    for kv in pairs:
        if "=" not in kv:
            print("跳过非法参数:", kv)
            continue
        d, g = kv.split("=", 1)
        if not (d.isdigit() and g.isdigit()):
            print("跳过非数字:", kv)
            continue
        locked[d] = g
    if not locked:
        print("没有有效 GID")
        return
    info = AA.fetch_app_info(aid)
    blk = upsert_lock_block(aid, name, locked, info, note=note)
    print("[完成] 已锁定历史 GID，写入", LUA_PATH)
    print(blk)
    appinfo = os.path.join(P.find_steam_dir() or "<Steam目录>", "appcache", "appinfo.vdf")
    print("下一步：①完全关闭 Steam ②删 %s 冷启动 "
          "③确认 content_log 里 Downloading 的 GID 是锁定值 ④下完覆盖破解补丁后开玩" % appinfo)


def do_import(appid, path):
    aid, name, err = AA.resolve(str(appid))
    if err or not aid:
        print("解析失败:", err)
        return
    lvas, patch_files = find_patch_files(path)
    all_gids = {}
    for t in lvas:
        all_gids.update(extract_gids(t))
    print("破解包扫描: lua %d 个, 补丁文件 %d 个, 提取到 GID %d 条"
          % (len(lvas), len(patch_files), len(all_gids)))
    if not all_gids:
        print("未在包内 lua 里找到 setManifestid 历史 GID。")
        print("请把包里的锁定版 .lua 一起放进包，或用 --lock 手动给定 GID。")
        if patch_files:
            staged = stage_patch(aid, patch_files)
            print("已暂存 %d 个补丁文件到 %s" % (len(staged), os.path.join(PATCH_STORE, str(aid))))
        return
    info = AA.fetch_app_info(aid)
    blk = upsert_lock_block(aid, name, all_gids, info, note="导入破解包锁定版")
    staged = stage_patch(aid, patch_files)
    print("[完成] 锁定 GID:", all_gids)
    print("       写入", LUA_PATH)
    print("       暂存补丁", len(staged), "个到", os.path.join(PATCH_STORE, str(aid)))
    print(blk)
    appinfo = os.path.join(P.find_steam_dir() or "<Steam目录>", "appcache", "appinfo.vdf")
    print("下一步：①完全关闭 Steam ②删 %s 冷启动 "
          "③确认 content_log 的 Downloading GID 是锁定值 ④下完把暂存补丁按目录覆盖进游戏目录" % appinfo)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="D 加密游戏版本锁定 + 破解包导入")
    p.add_argument("appid", nargs="?", help="游戏名 / AppID")
    p.add_argument("--import", dest="imp", help="导入破解包(zip/目录/lua)")
    p.add_argument("--lock", nargs="*", help="直接给 depotid=gid 锁定")
    p.add_argument("--list-lib", action="store_true", help="列出破解库")
    p.add_argument("--add-lib", nargs=4, metavar=("APPID", "NAME", "CRACK", "SOURCE"),
                   help="手动补一条破解库记录")
    a = p.parse_args()
    if a.list_lib:
        lib = load_library()
        print(json.dumps(lib, ensure_ascii=False, indent=2))
    elif a.add_lib:
        aid, nm, crack, src = a.add_lib
        lib = load_library()
        lib[aid] = {"name": nm, "crack": crack, "source": src,
                    "version": "", "locked_gids": {}, "verified": False}
        save_library(lib)
        print("[完成] 已写入破解库:", aid, nm)
    elif not a.appid:
        p.print_help()
    elif a.imp:
        do_import(a.appid, a.imp)
    elif a.lock is not None:
        do_lock(a.appid, a.lock)
    else:
        plan(a.appid)
