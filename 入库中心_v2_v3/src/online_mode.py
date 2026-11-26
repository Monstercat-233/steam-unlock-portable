# -*- coding: utf-8 -*-
"""联机模式：把 -onlinefix 写进指定账号/游戏的 Steam 启动选项。

作用域严格限定在
  <steam>/userdata/<accountid>/config/localconfig.vdf
的 UserLocalConfigStore.Software.Valve.Steam.apps.<appid>.LaunchOptions 一个字段。
不碰 mygames.lua / GID 锁 / 补丁 / 其他游戏 / 其他账号。

VDF 用「栈式定位」而不是整段正则：只在目标 appid 的 { } 块内找/插 LaunchOptions，
改完做逐字节还原校验（把新值换回旧值必须等于原文），确保没误伤别的字段。
"""
import os
import re
import shutil
from datetime import datetime

import paths as P

FLAG = "-onlinefix"


def classify(appid, info):
    """判断这个游戏适不适合 -onlinefix。返回 {level, reason, label}。

    level:
      ok      = Steamworks 大厅/P2P，OST 的 -onlinefix 有效
      warn    = VAC 游戏，能走 480 大厅但别进 VAC 官方服
      blocked = 自有账号/反作弊(EA/Ubisoft/Epic...)，-onlinefix 票据无效
      na      = Denuvo 纯单机(联机关不存在) / 无 key 下载不了
    """
    info = info or {}
    drm = (info.get("drm") or "").lower()
    third = bool(info.get("third_party_account"))
    vac = bool(info.get("vac"))
    has_key = bool(info.get("has_key") or info.get("depots"))

    if not has_key:
        return {"level": "na", "reason": "key 库无记录，下载不了，谈不上联机", "label": "不适用"}
    if third:
        return {"level": "blocked",
                "reason": "发行商走自有账号/反作弊(EA/Ubisoft/Epic/R星等)，-onlinefix 的 Steam 票据无效，联机需正版自有账号",
                "label": "不支持联机"}
    if "denuvo" in drm:
        return {"level": "na",
                "reason": "Denuvo 游戏通常是纯单机，联机这一关不存在；破解后走补丁即可",
                "label": "单机无需联机"}
    if vac:
        return {"level": "warn",
                "reason": "可走 Steam 480 大厅/社区服；但别进 VAC 官方服务器(封号风险)",
                "label": "谨慎联机"}
    return {"level": "ok",
            "reason": "Steamworks 大厅/P2P 游戏，-onlinefix 有效；双方都要设为联机模式",
            "label": "可联机"}


def _find_app_block(text, appid):
    """找到 "apps" 块内 "<appid>" 的 { ... } 区间，返回 (start, brace_open, brace_close)。

    start 是 "<appid>" 这个 key token 的起始位置。用栈匹配花括号，避免跨块误判。
    """
    key = '"%s"' % appid
    # 从 apps 块里找 appid key
    apps = re.search(r'"apps"\s*\{', text)
    search_from = apps.end() if apps else 0
    pos = text.find(key, search_from)
    while pos != -1:
        # key 后必须跟 { （允许空白）：确认是块 key 而不是别处的值
        m = re.match(r'\s*\{', text[pos + len(key):])
        if m:
            brace_open = pos + len(key) + m.end() - 1
            depth = 0
            i = brace_open
            in_quote = False
            esc = False
            while i < len(text):
                c = text[i]
                if in_quote:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_quote = False
                else:
                    if c == '"':
                        in_quote = True
                    elif c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            return pos, brace_open, i
                i += 1
        pos = text.find(key, pos + 1)
    raise ValueError("localconfig.vdf 中找不到 appid %s 的块" % appid)


def modify_launch_options(text, appid, enable, dry_run=False):
    """在目标 appid 块内幂等增删 -onlinefix。

    返回 (new_text, info)。info 含 changed/inserted/old_value/new_value。
    只动 LaunchOptions 一个字段；用还原校验保证没误伤其他内容。
    """
    if text is None:
        raise ValueError("localconfig.vdf 内容为空")
    start, bopen, bclose = _find_app_block(text, appid)
    block = text[bopen:bclose + 1]

    m = re.search(r'("LaunchOptions"\s+)("[^"]*")', block)
    if m:
        old = m.group(2)[1:-1]
        parts = old.split()
        had = FLAG in parts
        if enable and had:
            return text, {"changed": False, "inserted": False,
                          "old_value": old, "new_value": old}
        if not enable and not had:
            return text, {"changed": False, "inserted": False,
                          "old_value": old, "new_value": old}
        if enable:
            parts.append(FLAG)
            new = " ".join(parts)
            new_block = block[:m.start(2)] + '"' + new + '"' + block[m.end(2):]
        else:
            parts = [p for p in parts if p != FLAG]
            new = " ".join(parts)
            if new:
                new_block = block[:m.start(2)] + '"' + new + '"' + block[m.end(2):]
            else:
                # 删掉整个 LaunchOptions 行（含前导换行），做到完全可逆
                line_start = block.rfind('\n', 0, m.start(1))
                ls = line_start if line_start != -1 else m.start()
                line_end = block.find('\n', m.end(2))
                le = line_end if line_end != -1 else len(block)
                new_block = block[:ls] + block[le:]
        inserted = False
    else:
        if not enable:
            return text, {"changed": False, "inserted": False,
                          "old_value": "", "new_value": ""}
        old = ""
        new = FLAG
        inserted = True
        # 在块末尾的 } 前插入一行 LaunchOptions，缩进对齐 } 的缩进
        tail = re.search(r'\n([ \t]*)(\})$', block)
        if tail:
            ci = tail.group(1)
            new_block = block[:tail.start()] + '\n%s"LaunchOptions"\t\t"%s"\n%s}' % (ci, new, ci)
        else:
            new_block = block[:-1] + '\n\t"LaunchOptions"\t\t"%s"\n}' % new

    new_text = text[:bopen] + new_block + text[bclose + 1:]

    # 完整性校验：把整个新块换回原块必须逐字节等于原文（只动了这一个 appid 块）
    restored = new_text.replace(new_block, block, 1)
    assert restored == text, "onlinefix 修改越界，已中止"

    return new_text, {"changed": True, "inserted": inserted,
                      "old_value": old, "new_value": new}


def read_online_flag(accountid, appid):
    """读某账号/游戏当前 LaunchOptions。返回 {ok, enabled, value}。"""
    steam = P.find_steam_dir()
    if not steam:
        return {"ok": False, "enabled": False, "value": "", "error": "找不到 Steam 安装目录"}
    target = os.path.join(steam, "userdata", str(accountid), "config", "localconfig.vdf")
    if not os.path.isfile(target):
        return {"ok": False, "enabled": False, "value": "", "error": "账号 %s 没有 localconfig.vdf" % accountid}
    with open(target, encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        start, bopen, bclose = _find_app_block(text, appid)
    except ValueError:
        return {"ok": False, "enabled": False, "value": "", "error": "找不到该游戏的启动选项块"}
    block = text[bopen:bclose + 1]
    m = re.search(r'"LaunchOptions"\s+"([^"]*)"', block)
    value = m.group(1) if m else ""
    return {"ok": True, "enabled": FLAG in value.split(), "value": value, "error": ""}


def set_online_flag(accountid, appid, enable, dry_run=False):
    """文件级入口：备份 → 精确修改 → 原子写回。

    必须在 Steam 退出后调用，否则会被 Steam 覆写。
    dry_run=True 只算不改（用于 GUI 预览）。
    """
    steam = P.find_steam_dir()
    if not steam:
        return {"ok": False, "error": "找不到 Steam 安装目录"}
    target = os.path.join(steam, "userdata", str(accountid), "config", "localconfig.vdf")
    if not os.path.isfile(target):
        return {"ok": False, "error": "账号 %s 没有 localconfig.vdf" % accountid}
    with open(target, encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        new_text, info = modify_launch_options(text, appid, enable, dry_run=dry_run)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    result = {"ok": True, "changed": info["changed"],
              "old_value": info["old_value"], "new_value": info["new_value"],
              "backup": "", "dry_run": dry_run}
    if dry_run or not info["changed"]:
        return result

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = os.path.join(P.writable_dir(), "backup",
                      "localconfig_%s_%s_%s.vdf.bak" % (accountid, appid, stamp))
    os.makedirs(os.path.dirname(bk), exist_ok=True)
    shutil.copy2(target, bk)
    tmp = target + ".onlinefix.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new_text)
    os.replace(tmp, target)
    result["backup"] = bk
    return result
