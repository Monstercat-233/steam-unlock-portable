# -*- coding: utf-8 -*-
"""
denuvo_helper.py —— Denuvo 游戏运行关的半自动助手

自动部分：
  * 检测游戏是否 Denuvo（复用 auto_adapt.fetch_app_info）
  * 判断纯单机 / 联网，给出该走"票据"还是"补丁"的明确路线
  * 生成带 setAppTicket/setETicket 槽位的 lua 块（票据一填就生效）
  * 用 Steam API 自动填入已登录账号缓存的 AppTicket（若本机账号拥有该游戏）

手动部分（自动化碰不到，涉及账号凭证/第三方文件）：
  * 真拥有者账号提取票据：需拥有者登录 Steam + 启动游戏，用 extract_tickets 抓取
  * Denuvo 绕过补丁：需下载对应 build 的 crack 并替换文件

用法：
  python denuvo_helper.py 3489700          # 查剑星该怎么过 Denuvo 这关
  python denuvo_helper.py 3489700 --ticket HEX   # 填入 AppTicket 生成 lua 块
  python denuvo_helper.py 3489700 --apply        # 把带票据槽位的块写入库
"""
import sys, os, re, json, argparse
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


def denuvo_plan(appid, info=None):
    """返回 (是否Denuvo, 是否纯单机, 路线字符串, 详细步骤)"""
    info = info or AA.fetch_app_info(appid)
    drm = (info.get("drm") or "").lower()
    if "denuvo" not in drm:
        return False, None, "无需处理", "该游戏无 Denuvo，addappid 后直接玩。"
    third = bool(info.get("third_party_account"))
    online = third or "online" in drm
    if third:
        route = "放弃联机"
        steps = (
            "自有账号+内核反作弊(EA/Ubisoft等)：票据和补丁都救不了联机，"
            "单机部分若想玩只能走 Denuvo 补丁。"
        )
    elif online:
        route = "票据为主"
        steps = "联网 Denuvo 游戏：需真账号票据 + -onlinefix。"
    else:
        route = "补丁优先"
        steps = (
            "纯单机 Denuvo：【首选】下载对应 build 的 Denuvo 绕过补丁，"
            "备份原 exe 后替换，一次搞定；【备选】真拥有者账号 extract_tickets "
            "提取 AppTicket/ETicket(30分钟有效)，用 --ticket 填入 lua。"
        )
    return True, not online, route, steps


def ticket_block(appid, name, info=None, app_ticket=None, e_ticket=None):
    """生成带 setAppTicket/setETicket 的幂等块（在 auto_adapt 块基础上追加票据行）。"""
    info = info or AA.fetch_app_info(appid)
    blk = AA.build_block(appid, name or "", info=info, mark_fmt=MARK_FMT, end=END_MARK)
    lines = blk.rstrip("\n").split("\n")
    # 插到 END_MARK 之前
    extra = []
    if app_ticket:
        extra.append('setAppTicket(%d, "%s")' % (appid, app_ticket))
    if e_ticket:
        extra.append('setETicket(%d, "%s")' % (appid, e_ticket))
    if not app_ticket and not e_ticket:
        extra.append("-- 票据槽位：真账号提取后填这里 -> setAppTicket(%d, \"HEX\")" % appid)
    end = lines.pop()  # END_MARK
    return "\n".join(lines + extra + [end]) + "\n"


def cmd(appid, args):
    aid, name, err = AA.resolve(str(appid))
    if err or not aid:
        print("解析失败:", err); return
    info = AA.fetch_app_info(aid)
    is_denuvo, single, route, steps = denuvo_plan(aid, info)
    print("=" * 60)
    print("游戏:", info.get("name") or name, "(AppID %d)" % aid)
    print("DRM :", repr(info.get("drm")))
    print("下载:", "OK (%d depot)" % len(info.get("depots", {})) if info.get("depots") else "无 key")
    print("Denuvo:", "是" if is_denuvo else "否", "| 纯单机:" if is_denuvo else "", single if is_denuvo else "")
    print("路线:", route)
    print("说明:", steps)
    print("=" * 60)
    if args.ticket or args.apply:
        blk = ticket_block(aid, name, info, args.ticket, args.eticket)
        if args.apply:
            txt = ""
            if os.path.isfile(lua_path()):
                txt = open(lua_path(), encoding="utf-8", errors="replace").read()
            txt = re.sub(r"%s\n.*?%s\n" % (re.escape(MARK_FMT.format(aid)), re.escape(END_MARK)),
                         "", txt, flags=re.S)
            if txt and not txt.endswith("\n"):
                txt += "\n"
            open(lua_path(), "w", encoding="utf-8").write(txt + blk)
            print("[完成] 已写入带票据槽位的块到", lua_path())
        print(blk)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Denuvo 游戏运行助手")
    p.add_argument("appid", help="游戏名 / AppID")
    p.add_argument("--ticket", help="AppTicket (hex)")
    p.add_argument("--eticket", help="ETicket (hex)")
    p.add_argument("--apply", action="store_true", help="写入带票据槽位的 lua 块")
    a = p.parse_args()
    cmd(a.appid, a)
