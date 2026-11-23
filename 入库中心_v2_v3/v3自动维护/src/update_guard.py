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
        return {
            "buildid": buildid,
            "target_buildid": target or buildid,
            "install_dir": install,
            "manifest_gids": gids,
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
    return "\n".join(lines)
