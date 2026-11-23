# -*- coding: utf-8 -*-
"""配置快照 / 一键回滚 / 配置体检 / 操作审计。回滚前强制要求 Steam 已退出。"""
import os
import re
import json
import shutil
import hashlib
import datetime

import paths as P

SNAPSHOT_ROOT = os.path.join(P.writable_dir(), "snapshots")
AUDIT_PATH = os.path.join(P.writable_dir(), "audit.log")

KNOWN_DLL_HASHES = {
    "dwmapi.dll": "FE82F35C02CB81FEBF070EF3B9194FF5D52EE526608BF3DE76D09E04C5B20DF1",
    "xinput1_4.dll": "0234A56A72121FD3DD50FF533F1A6E670033DBC2D92EF98551E8903CFF402250",
    "OpenSteamTool.dll": "705B31DC1C0335F5519BCB938ED589BA6909F3AAB6B7B89495C1569A951210D5",
}

steam_running = P.steam_running  # 模块级别名，便于 monkeypatch 与 GUI 直接判断


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def default_targets(accountid=None):
    steam = P.find_steam_dir()
    if not steam:
        return []
    targets = [
        os.path.join(steam, "config", "stplug-in", "mygames.lua"),
        os.path.join(steam, "opensteamtool.toml"),
    ]
    if accountid:
        user = os.path.join(steam, "userdata", str(accountid), "config")
        targets += [
            os.path.join(user, "config.vdf"),
            os.path.join(user, "localconfig.vdf"),
        ]
    targets.append(os.path.join(steam, "config", "loginusers.vdf"))
    return [t for t in targets if os.path.isfile(t)]


def snapshot(targets=None, label=""):
    if targets is None:
        targets = default_targets()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = stamp + ("_" + label if label else "")
    d = os.path.join(SNAPSHOT_ROOT, name)
    os.makedirs(d, exist_ok=True)
    manifest = []
    for i, src in enumerate(targets):
        if not os.path.isfile(src):
            continue
        base = os.path.basename(src)
        out = os.path.join(d, "%02d_%s" % (i, base))
        shutil.copy2(src, out)
        manifest.append({
            "orig_path": src, "file": os.path.basename(out),
            "sha256": _sha256(out), "size": os.path.getsize(out),
        })
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    audit("snapshot", paths_=[os.path.basename(x) for x in targets])
    return d


def rollback(snapshot_dir):
    if P.steam_running():
        return False
    mf = os.path.join(snapshot_dir, "manifest.json")
    if not os.path.isfile(mf):
        return False
    try:
        manifest = json.load(open(mf, encoding="utf-8"))
    except Exception:
        return False
    for item in manifest:
        f = os.path.join(snapshot_dir, item["file"])
        if not os.path.isfile(f):
            return False
        if _sha256(f) != item["sha256"] or os.path.getsize(f) != item["size"]:
            return False
    # 回滚前先给当前状态打快照，方便反悔
    try:
        snapshot(label="pre_rollback")
    except Exception:
        pass
    for item in manifest:
        f = os.path.join(snapshot_dir, item["file"])
        dst = item["orig_path"]
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(f, dst)
    audit("rollback", paths_=[os.path.basename(i["orig_path"]) for i in manifest])
    return True


def health_check():
    steam = P.find_steam_dir()
    out = {
        "family_share": False, "lua_blocks_paired": False,
        "lua_block_count": 0, "dll_hashes": {}, "steam_found": bool(steam),
    }
    if not steam:
        return out
    acc = P.current_account()
    if acc:
        lc = os.path.join(steam, "userdata", str(acc["accountid"]), "config", "localconfig.vdf")
        if os.path.isfile(lc):
            txt = open(lc, encoding="utf-8", errors="replace").read()
            out["family_share"] = ("FamilyGroup" in txt or "SharedAuth" in txt)
    lua = P.lua_path()
    if os.path.isfile(lua):
        txt = open(lua, encoding="utf-8", errors="replace").read()
        nb = txt.count("-- #OSTBLOCK:")
        ne = txt.count("-- #OSTENDBLOCK")
        out["lua_block_count"] = nb
        out["lua_blocks_paired"] = (nb == ne)
    for name, expect in KNOWN_DLL_HASHES.items():
        f = os.path.join(steam, name)
        if os.path.isfile(f):
            out["dll_hashes"][name] = "OK" if _sha256(f).upper() == expect.upper() else "MISMATCH"
        else:
            out["dll_hashes"][name] = "MISSING"
    return out


def audit(action, appid="", paths_=None):
    try:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        line = "%s | %s | %s | %s\n" % (ts, action, appid, ",".join(paths_ or []))
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
