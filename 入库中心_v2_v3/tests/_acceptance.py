# -*- coding: utf-8 -*-
r"""验收脚本：全部写操作指向临时目录，绝不碰真实 D:\STEAM 运行副本。"""
import sys, os, json, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import version_lock as V, apply_patch as AP, game_index as G, backup as B, auto_adapt as AA

tmp = tempfile.mkdtemp(prefix="ruku_accept_")
results = {}

# 验收2: 入库块写入 + 幂等（临时 lua）
lua = os.path.join(tmp, "mygames.lua")
open(lua, "w", encoding="utf-8").close()
old_lua = V.LUA_PATH; V.LUA_PATH = lua
info = AA.fetch_app_info(550)
for _ in range(3):
    V.upsert_lock_block(550, info.get("name", "L4D2"), {}, info)
txt = open(lua, encoding="utf-8").read()
results["2_入库幂等"] = "PASS" if txt.count("-- #OSTBLOCK:550") == 1 and "addappid(550" in txt else "FAIL"
V.LUA_PATH = old_lua

# 验收3: 版本锁定库列剑星 + 锁定 GID
lib = V.load_library()
jx = lib.get("3489700") or {}
results["3_版本锁定"] = "PASS" if jx.get("locked_gids") and len(jx["locked_gids"]) == 3 else "FAIL"

# 验收4: 补丁 dry-run 扫描（只读）
crack = r"D:\STEAM入库\剑星+破解补丁\_crack_ready"
if os.path.isdir(crack):
    items = AP.collect_patch_files(crack, os.path.join(tmp, "unzip"))
    rels = [r for r, _ in items]
    results["4_补丁扫描"] = "PASS(%d文件)" % len(items) if any("SB-Win64-Shipping.exe" in r for r in rels) else "FAIL(no exe)"
else:
    results["4_补丁扫描"] = "SKIP(目录不存在)"

# 验收5: 快照 manifest + 体检（快照写临时，体检只读）
src = os.path.join(tmp, "cfg.vdf"); open(src, "w", encoding="utf-8").write("abc")
old_root = B.SNAPSHOT_ROOT; B.SNAPSHOT_ROOT = os.path.join(tmp, "snaps")
d = B.snapshot([src], label="accept")
mf = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
h = B.health_check()
B.SNAPSHOT_ROOT = old_root
ok_snap = mf[0]["size"] == 3 and len(mf[0]["sha256"]) == 64
ok_health = h.get("lua_blocks_paired") and all(v == "OK" for v in h.get("dll_hashes", {}).values())
results["5_快照体检"] = "PASS" if ok_snap and ok_health else "FAIL(snap=%s health=%s)" % (ok_snap, ok_health)

# 验收6: 名字检索（临时 names，纯离线）
namesf = os.path.join(tmp, "names.json")
json.dump({"3489700": "Stellar Blade", "2358720": "Black Myth Wukong"}, open(namesf, "w", encoding="utf-8"), ensure_ascii=False)
old_n = G.NAMES_PATH; G.NAMES_PATH = namesf
hits = G.search("Stellar")
G.NAMES_PATH = old_n
results["6_名字检索"] = "PASS" if (3489700, "Stellar Blade") in hits else "FAIL"

shutil.rmtree(tmp, ignore_errors=True)
for k, v in results.items():
    print("%s = %s" % (k, v))
print("ALL_OK =", all(str(v).startswith("PASS") or str(v).startswith("SKIP") for v in results.values()))
