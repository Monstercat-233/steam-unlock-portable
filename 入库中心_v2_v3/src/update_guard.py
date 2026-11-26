"""本体版本更新检测（纯只读）。

只读取 Steam appmanifest / libraryfolders / crack_library；唯一写操作是
baseline.json，且通过临时文件 + os.replace 原子落盘。已锁定游戏永不在此处
自动刷新 GID，也永不下载补丁。
"""
import json
import os
import re
from datetime import datetime

import paths as P


BASELINE_PATH = os.path.join(P.writable_dir(), "baseline.json")

# 模块级别名：与 P.writable_dir 同源，便于测试注入隔离的备份目录。
writable_dir = P.writable_dir

_ADVICE = (
    "本体疑似被更新，补丁可能失效：请到版本锁定 tab 重锁重打，"
    "确认前不要启动游戏。"
)


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def library_dirs():
    """返回所有 Steam 库根目录；主库 + libraryfolders.vdf 中的 path，去重保序。"""
    steam = P.find_steam_dir()
    if not steam:
        return []
    dirs = []
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    text = _read_text(vdf)
    if text:
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            d = os.path.normpath(raw.replace("\\\\", "\\"))
            if d not in dirs:
                dirs.append(d)
    steam = os.path.normpath(steam)
    if steam not in dirs:
        dirs.append(steam)
    return dirs


def read_acf(appid, dirs=None):
    """解析 appmanifest_<appid>.acf；找不到返回 None。"""
    dirs = dirs if dirs is not None else library_dirs()
    for d in dirs:
        acf = os.path.join(d, "steamapps", f"appmanifest_{appid}.acf")
        text = _read_text(acf)
        if text is None:
            continue

        def field(name):
            m = re.search(r'"' + re.escape(name) + r'"\s+"([^"]*)"', text)
            return m.group(1) if m else ""

        buildid = field("buildid")
        if not buildid:
            # acf 存在但内容为空/损坏：视为该库无有效记录，继续找下一库。
            continue
        target = field("TargetBuildID")
        install = field("installdir")
        gids = dict(re.findall(r'"(\d{4,})"\s*\{\s*"manifest"\s+"(\d+)"', text))
        # 自动更新预约字段：只用于启动告警，不进基线（避免基线本身记 1 导致漏报）。
        auto_behavior = field("AutoUpdateBehavior") or "0"
        scheduled = field("ScheduledAutoUpdate") or "0"
        return {
            "buildid": buildid,
            "target_buildid": target or buildid,
            "install_dir": install,
            "manifest_gids": gids,
            "auto_update_behavior": auto_behavior,
            "scheduled_auto_update": scheduled,
        }
    return None


def locked_apps():
    """只返回 verified 且带 locked_gids 的锁定游戏。"""
    path = os.path.join(P.writable_dir(), "crack_library.json")
    text = _read_text(path)
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    out = {}
    for appid, rec in data.items():
        if isinstance(rec, dict) and rec.get("verified") and rec.get("locked_gids"):
            out[str(appid)] = rec
    return out


def reset_auto_update():
    """把已锁定游戏的 appmanifest 自动更新字段归零（纯本地，改前备份）。

    只动 crack_library 中 verified 且带 locked_gids 的游戏；未锁定游戏不碰。
    每个要改的 acf 先原样备份到 <writable_dir>/backup/appmanifest_<appid>_<stamp>.acf，
    再把 AutoUpdateBehavior/ScheduledAutoUpdate 的引号值替换为 "0"。
    必须在 Steam 退出后调用，否则改动会被 Steam 覆写。
    返回 {changed:[appid,...], backups:{appid:path}}。
    """
    result = {"changed": [], "backups": {}}
    locked = locked_apps()
    if not locked:
        return result
    dirs = library_dirs()
    import shutil as _sh
    from datetime import datetime as _dt

    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    backup_root = os.path.join(writable_dir(), "backup")
    for appid in locked:
        target = None
        for d in dirs:
            acf = os.path.join(d, "steamapps", "appmanifest_%s.acf" % appid)
            if os.path.isfile(acf):
                target = acf
                break
        if not target:
            continue
        try:
            text = _read_text(target)
            if text is None:
                continue
            new = re.sub(r'("AutoUpdateBehavior"\s+")[^"]*(")', r'\g<1>0\g<2>', text)
            new = re.sub(r'("ScheduledAutoUpdate"\s+")[^"]*(")', r'\g<1>0\g<2>', new)
            if new == text:
                continue  # 已经是 0，无需改动
            os.makedirs(backup_root, exist_ok=True)
            bk = os.path.join(backup_root, "appmanifest_%s_%s.acf.bak" % (appid, stamp))
            _sh.copy2(target, bk)
            with open(target, "w", encoding="utf-8") as f:
                f.write(new)
            result["changed"].append(appid)
            result["backups"][appid] = bk
        except OSError:
            continue
    return result


def _load_baseline():
    text = _read_text(BASELINE_PATH)
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_baseline(force=False):
    """为锁定游戏建立/补全版本基线；已有条目在非 force 时保留。"""
    baseline = _load_baseline()
    for appid, rec in locked_apps().items():
        if not force and str(appid) in baseline:
            continue
        current = read_acf(int(appid))
        if current is None:
            continue
        baseline[str(appid)] = {
            "name": rec.get("name", ""),
            "buildid": current["buildid"],
            "target_buildid": current["target_buildid"],
            "manifest_gids": dict(current["manifest_gids"]),
            "captured_at": datetime.now().isoformat(timespec="seconds"),
        }
    _atomic_write_json(BASELINE_PATH, baseline)
    return baseline


def check_updates():
    """比对基线与当前 acf，返回需要人工处理的告警项列表。"""
    baseline = _load_baseline()
    apps = locked_apps()
    items = []
    for appid, rec in apps.items():
        base = baseline.get(str(appid))
        if not base:
            continue
        current = read_acf(int(appid))
        if current is None:
            continue
        reasons = []
        if current["buildid"] != base.get("buildid"):
            reasons.append(
                f"buildid 变化：基线 {base.get('buildid')} → 当前 {current['buildid']}"
            )
        if current["target_buildid"] != current["buildid"]:
            reasons.append(
                f"TargetBuildID({current['target_buildid']}) != buildid({current['buildid']})，"
                "Steam 已下发待更新"
            )
        locked_gids = rec.get("locked_gids") or {}
        for depot, gid in locked_gids.items():
            now = current["manifest_gids"].get(str(depot))
            if now != gid:
                reasons.append(f"depot {depot} manifest 变化：锁定 {gid} → 当前 {now}")
        # 第 4 判据：Steam 被设成自动更新/已预约更新时间（与 v1.4.1 锁定版冲突）。
        auto_behavior = current.get("auto_update_behavior", "0")
        scheduled = current.get("scheduled_auto_update", "0")
        if auto_behavior not in ("", "0") or scheduled not in ("", "0"):
            reasons.append(
                f"自动更新被开启：AutoUpdateBehavior={auto_behavior}，"
                f"ScheduledAutoUpdate={scheduled}；"
                "请停止 Steam 后把这两项改为 0 并冷启动（Steam 运行时改会被覆盖）"
            )
        if reasons:
            items.append({
                "appid": str(appid),
                "name": rec.get("name", ""),
                "reasons": reasons,
                "current": current,
                "baseline": base,
                "advice": _ADVICE,
            })
    return items


def format_report(items):
    """把告警项渲染成多行中文报告；无告警返回固定短句。"""
    if not items:
        return "本体版本检测：未发现已锁定游戏被更新。"
    lines = ["本体版本更新检测告警（补丁可能失效）："]
    for it in items:
        lines.append(f"- {it.get('name', '')} (appid {it.get('appid', '')})")
        for reason in it.get("reasons", []):
            lines.append(f"    · {reason}")
        lines.append(f"    建议：{it.get('advice', '')}")
    lines.append("请到版本锁定 tab 重锁重打后再启动游戏。")
    lines.append(
        "若为自动更新告警：停 Steam → 备份 appmanifest_<appid>.acf → "
        "把 AutoUpdateBehavior 与 ScheduledAutoUpdate 改为 0 → 冷启动。"
    )
    return "\n".join(lines)
