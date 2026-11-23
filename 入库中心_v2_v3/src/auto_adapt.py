# -*- coding: utf-8 -*-
"""
auto_adapt.py —— OpenSteamTool 全自动入库适配核心

目标：用户只给一个游戏名 / AppID，自动完成：
  1. 联网解析 AppID、游戏名（本地表 → Steam storesearch API）
  2. 从 steamcmd.net 拉该游戏的完整 depot 列表 + 每个 depot 的实时 manifest GID
  3. 从 ManifestHub 全量 depot key 库（28.8 万条，本地缓存，7 天刷新）取每个 depot 的解密 key
  4. 从 Steam appdetails 读第三方 DRM（Denuvo 等）标记
  5. 生成完整幂等 Lua 块：主 addappid + 每个带 key 的 depot + setManifestid
  6. 给出"能不能下载 / 有没有 Denuvo / 能不能联机"的判断

设计原则：
  - 全联网自动，零手工补 key；本地缓存加速，失败自动降级到本地库
  - 每个网络请求都有超时和降级，任何一处失败都不影响入库（最坏退化成裸 addappid）
  - 生成的块带唯一标记，重复添加覆盖式写入，绝不累积孤儿行
"""
import os, re, json, time, threading, urllib.request, urllib.parse, sys
import paths as P

HERE = P.resource_dir()
# key 库优先读 exe 同目录（可独立更新），否则退回随包只读目录；缺失时不联网、返回空库
_wk = os.path.join(P.writable_dir(), "depotkeys_master.json")
_rk = os.path.join(P.resource_dir(), "depotkeys_master.json")
MASTER_KEYS_PATH = _wk if os.path.isfile(_wk) else _rk
CACHE_META_PATH = os.path.join(P.writable_dir(), "auto_adapt_cache.json")    # appid -> {info, ts}（可写）
MASTER_KEYS_URL = ("https://raw.githubusercontent.com/SteamAutoCracks/"
                   "ManifestHub/master/depotkeys.json")
STEAMCMD_INFO = "https://api.steamcmd.net/v1/info/{appid}"
APPDETAILS = "https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english"
STORESEARCH = ("https://store.steampowered.com/api/storesearch/?term={q}&l=schinese&cc=CN")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MASTER_TTL = 7 * 24 * 3600      # 全量 key 库 7 天刷新一次
APP_TTL = 6 * 3600              # 单游戏 depot/manifest 6 小时刷新
CACHE_VERSION = 2               # 逻辑变更时+1，强制旧缓存失效重拉
# Steamworks 公共可再发行组件 depot（几乎所有游戏都挂）：不能当游戏本体 key，
# 否则无 key 的游戏会被误判为"可下载"，且每次入库都塞垃圾行。
COMMON_DEPOTS = {"228989", "228990"}
_kv_lock = threading.Lock()
_app_cache = None
_key_db = None
_key_db_ts = 0

BUILTIN = {
    "left 4 dead 2": 550, "l4d2": 550, "求生之路2": 550,
    "counter-strike 2": 730, "cs2": 730, "csgo": 730,
    "dota 2": 570, "dota2": 570, "pubg": 578080, "绝地求生": 578080,
    "apex legends": 1172470, "apex": 1172470,
    "hades": 1145360, "hades ii": 1145350, "hades 2": 1145350,
    "hollow knight": 367520, "空洞骑士": 367520,
    "stardew valley": 413150, "星露谷物语": 413150,
    "grand theft auto v": 271590, "gta5": 271590, "gta v": 271590,
    "cyberpunk 2077": 1091500, "赛博朋克2077": 1091500,
    "elden ring": 1245620, "艾尔登法环": 1245620,
    "the witcher 3": 292030, "巫师3": 292030,
    "terraria": 105600, "泰拉瑞亚": 105600,
    "rimworld": 294100, "环世界": 294100, "factorio": 427520,
    "dead by daylight": 381210, "黎明杀机": 381210,
    "payday 2": 218620, "warframe": 230410, "destiny 2": 1085660,
    "satisfactory": 526870, "valheim": 892970, "palworld": 1623730,
    "幻兽帕鲁": 1623730, "black myth: wukong": 2358720,
    "黑神话悟空": 2358720, "wukong": 2358720,
    "phantom blade zero": 4115450, "影之刃零": 4115450,
    "battlefield 6": 2807960, "战地六": 2807960, "战地6": 2807960, "bf6": 2807960,
    "hogwarts legacy": 990080, "baldur's gate 3": 1086940,
    "bg3": 1086940, "博德之门3": 1086940,
    "red dead redemption 2": 1174180, "rdr2": 1174180,
    "fallout 4": 377160, "skyrim": 489830, "civilization vi": 289070,
    "civ6": 289070, "cities: skylines": 255710, "portal 2": 620,
    "half-life 2": 220, "team fortress 2": 440, "tf2": 440,
    "garry's mod": 4000, "gmod": 4000, "rust": 252490, "dayz": 221100,
    "no man's sky": 275850, "subnautica": 264710, "深海迷航": 264710,
    "left 4 dead": 500, "borderlands 3": 397540,
    "monster hunter: world": 582660, "sekiro": 814380, "只狼": 814380,
    "dark souls 3": 374320, "resident evil 4": 2050650,
    "lethal company": 1966720, "dont starve together": 322330,
    "don't starve together": 322330, "wallpaper engine": 431960,
}


def _http(url, timeout=20, data=None):
    """返回 bytes；失败返回 None。"""
    try:
        if data is not None:
            req = urllib.request.Request(url, data=data, headers=UA)
        else:
            req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def refresh_master_keys(force=False):
    """下载/刷新全量 depot key 库；返回 dict(depot_id_str -> key)。失败用本地旧文件。"""
    global _key_db, _key_db_ts
    with _kv_lock:
        if _key_db is not None and not force and time.time() - _key_db_ts < MASTER_TTL:
            return _key_db
        # 先尝试本地文件
        local = None
        if os.path.isfile(MASTER_KEYS_PATH):
            try:
                local = json.load(open(MASTER_KEYS_PATH, "r", encoding="utf-8"))
                local_ts = os.path.getmtime(MASTER_KEYS_PATH)
            except Exception:
                local, local_ts = None, 0
        else:
            local_ts = 0
        # 缓存新鲜就直接用
        if local is not None and not force and time.time() - local_ts < MASTER_TTL:
            _key_db, _key_db_ts = local, time.time()
            return _key_db
        # 联网刷新
        data = _http(MASTER_KEYS_URL, timeout=90)
        if data and len(data) > 1000000:
            try:
                fresh = json.loads(data.decode("utf-8", "replace"))
                with open(MASTER_KEYS_PATH, "wb") as f:
                    f.write(data)
                _key_db, _key_db_ts = fresh, time.time()
                return _key_db
            except Exception:
                pass
        # 降级：用本地旧文件
        if local is not None:
            _key_db, _key_db_ts = local, time.time()
            return _key_db
        _key_db, _key_db_ts = {}, time.time()
        return _key_db


def get_key_db():
    """只读随包 key 库；文件缺失返回空库，绝不因此联网卡住。显式刷新走 refresh_master_keys(force=True)。"""
    global _key_db, _key_db_ts
    if _key_db is None:
        if not os.path.isfile(MASTER_KEYS_PATH):
            return {}
        try:
            _key_db = json.load(open(MASTER_KEYS_PATH, "r", encoding="utf-8"))
            _key_db_ts = time.time()
        except Exception:
            return {}
    return _key_db


def resolve(arg):
    """返回 (appid, 显示名, err)。纯本地表/数字/链接不联网；名字才联网。"""
    arg = str(arg).strip()
    if not arg:
        return None, "", "空输入"
    m = re.search(r"/app/(\d+)", arg)
    if m:
        return int(m.group(1)), "", None
    if arg.isdigit():
        return int(arg), "", None
    aid = BUILTIN.get(arg.lower())
    if aid:
        return aid, arg, None
    data = _http(STORESEARCH.format(q=urllib.parse.quote(arg)), timeout=12)
    if data:
        try:
            items = json.loads(data.decode("utf-8", "replace")).get("items") or []
            if items:
                return items[0].get("id"), items[0].get("name") or arg, None
        except Exception:
            pass
    return None, "", "未查到该游戏，请直接用数字 AppID"


def _load_app_cache():
    global _app_cache
    if _app_cache is not None:
        return _app_cache
    _app_cache = {}
    if os.path.isfile(CACHE_META_PATH):
        try:
            _app_cache = json.load(open(CACHE_META_PATH, "r", encoding="utf-8"))
        except Exception:
            _app_cache = {}
    return _app_cache


def _save_app_cache():
    with _kv_lock:
        try:
            with open(CACHE_META_PATH, "w", encoding="utf-8") as f:
                json.dump(_app_cache, f, ensure_ascii=False)
        except Exception:
            pass


def fetch_app_info(appid, force=False):
    """
    联网拉单个游戏的完整适配信息。
    返回 dict:
      {name, drm, depots: {depotid: key}, manifest: {depotid: gid},
       has_key, steamworks, ok_download, ts}
    """
    cache = _load_app_cache()
    key = str(appid)
    cached = cache.get(key)
    if (cached and not force and cached.get("_v") == CACHE_VERSION
            and time.time() - cached.get("ts", 0) < APP_TTL):
        return cached

    keys = get_key_db()
    name, drm, publisher = "", "", ""
    depots, manifest = {}, {}

    # 1) steamcmd.net：depot 列表 + 实时 manifest GID
    raw = _http(STEAMCMD_INFO.format(appid=appid), timeout=25)
    if raw:
        try:
            node = json.loads(raw.decode("utf-8", "replace"))["data"][str(appid)]
            common = node.get("common") or {}
            name = common.get("name", "") or ""
            drm = common.get("drm_notice", "") or ""
            publisher = common.get("publisher", "") or ""
            if not drm:
                # Steam appdetails 补充 DRM 标记
                ad = _http(APPDETAILS.format(appid=appid), timeout=15)
                if ad:
                    d = json.loads(ad.decode("utf-8", "replace")).get(str(appid), {})
                    if d.get("success"):
                        data = d.get("data", {})
                        name = name or data.get("name", "")
                        drm = data.get("drm_notice", "") or ""
            depots_node = node.get("depots") or {}
            for did, dnode in depots_node.items():
                if not did.isdigit():
                    continue  # branches / privatebranches 等元数据
                if not isinstance(dnode, dict):
                    continue
                k = keys.get(str(did))
                # 公共组件 depot 只在游戏自身也有 key 时才纳入，避免误判无 key 游戏
                if k and re.fullmatch(r"[0-9a-fA-F]{64}", k or "") and did not in COMMON_DEPOTS:
                    depots[did] = k.lower()
                mfs = dnode.get("manifests") or {}
                pub = mfs.get("public") or {}
                gid = pub.get("gid")
                if gid:
                    manifest[did] = str(gid)
        except Exception:
            pass

    # 2) Steam appdetails 兜底（拿名字、DRM、发行商、VAC 标记）
    vac = False
    ad = _http(APPDETAILS.format(appid=appid), timeout=15)
    if ad:
        try:
            d = json.loads(ad.decode("utf-8", "replace")).get(str(appid), {})
            if d.get("success"):
                data = d.get("data", {})
                name = name or data.get("name", "")
                drm = drm or data.get("drm_notice", "") or ""
                publisher = publisher or data.get("publishers") and " / ".join(data["publishers"]) or ""
                cats = data.get("categories") or []
                vac = any(c.get("id") == 8 for c in cats)
        except Exception:
            pass

    # 3) 主 appid 自身的 key（steamcmd 有时不把主 appid 列在 depots 里）
    own_key = keys.get(key)
    if own_key and re.fullmatch(r"[0-9a-fA-F]{64}", own_key or ""):
        depots.setdefault(key, own_key.lower())

    # 自有账号/反作弊发行商 → -onlinefix 的 Steam 票据无效，联机走不通
    pub_lower = publisher.lower()
    third_party_account = any(p in pub_lower for p in (
        "electronic arts", "ubisoft", "microsoft", "activision", "riot games",
        "battlenet", "blizzard", "epic games", "rockstar games"))
    info = {
        "name": name,
        "drm": drm,
        "publisher": publisher,
        "vac": vac,
        "third_party_account": third_party_account,
        "depots": depots,
        "manifest": manifest,
        "has_key": bool(depots),
        "steamworks": not third_party_account and not any(
            x in drm.lower() for x in ("denuvo", "third-party", "3rd party")),
        "ok_download": bool(depots),
        "_v": CACHE_VERSION,
        "ts": time.time(),
    }
    cache[key] = info
    _save_app_cache()
    return info


def build_block(appid, name="", info=None, mark_fmt="-- #OSTBLOCK:{}", end="-- #OSTENDBLOCK"):
    """生成幂等 Lua 块（带标记）。info 为空时自动 fetch。"""
    info = info or fetch_app_info(appid)
    label = name or info.get("name") or str(appid)
    lines = [mark_fmt.format(appid)]
    depots = info.get("depots") or {}
    manifest = info.get("manifest") or {}
    if depots:
        tag = "全自动适配" if info.get("drm") == "" else "全自动适配(有DRM:%s)" % info["drm"]
        lines.append("-- %s  [%s]" % (label, tag))
        # 主 appid 优先
        if str(appid) in depots:
            lines.append('addappid(%d, 1, "%s")' % (appid, depots[str(appid)]))
        else:
            lines.append("addappid(%d)" % appid)
        for did, k in depots.items():
            if str(did) != str(appid):
                lines.append('addappid(%s, 1, "%s")' % (did, k))
        for did, gid in manifest.items():
            if did in depots or str(did) == str(appid):
                # setManifestid 第一个参数必须是数字(depot id)，写成字符串会被静默忽略
                # 导致锁定 GID 失效、下载仍走实时最新版。参见 README_ZH.md 官方签名。
                did_arg = str(did) if str(did).isdigit() else '"%s"' % did
                lines.append('setManifestid(%s, "%s")' % (did_arg, gid))
    else:
        lines.append("-- %s  [key 库无记录，仅显示图标]" % label)
        lines.append("addappid(%d)" % appid)
    lines.append(end)
    return "\n".join(lines) + "\n"


def judge(appid, info=None):
    """返回 (可下载, 可运行, 可联机, 说明)。可运行/可联机也可能是字符串提示。"""
    info = info or fetch_app_info(appid)
    drm = (info.get("drm") or "").lower()
    has_denuvo = "denuvo" in drm
    third = bool(info.get("third_party_account"))
    vac = bool(info.get("vac"))
    ok_dl = bool(info.get("depots"))
    if not ok_dl:
        return False, False, False, "全网无 depot key → 只能入库看图标，下载不了"
    if third:
        return True, "需自有账号", False, (
            "发行商走自有账号+反作弊(EA/Ubisoft/Microsoft等)：下载 OK，"
            "但 -onlinefix 的 Steam 票据无效，联机需正版自有账号，强反作弊会封号")
    if has_denuvo:
        # 纯单机 Denuvo 游戏联机那关不存在，按是否自带在线组件粗判
        online_part = bool(info.get("third_party_account")) or any(
            m in (info.get("drm") or "").lower() for m in ("online", "multiplayer"))
        online_tag = "需票据" if online_part else "单机无需"
        return True, "需票据/补丁", online_tag, (
            "有 Denuvo：下载 OK；运行需【票据】(真账号 extract_tickets 提取,30分钟有效) "
            "或【Denuvo 绕过补丁】(推荐,一次搞定)。纯单机不用管联机。")
    if vac:
        return True, True, "避开VAC", "可下载/运行；联机别进 VAC 官方服务器(封号)，走社区/480大厅"
    return True, True, True, "无第三方 DRM：下载/运行/联机全走 Steam 票据，OST 可直接玩"


if __name__ == "__main__":
    import sys
    print("刷新全量 key 库…")
    db = refresh_master_keys()
    print("key 库条数:", len(db))
    for a in sys.argv[1:] or ["2358720", "2807960", "4115450", "550"]:
        print("\n===== AppID", a, "=====")
        info = fetch_app_info(int(a))
        print("名称:", info["name"], "| DRM:", repr(info["drm"]))
        print("有key:", info["has_key"], "| depot 数:", len(info["depots"]), "| manifest 数:", len(info["manifest"]))
        print("判断:", judge(int(a), info))
        print(build_block(int(a), info=info))
