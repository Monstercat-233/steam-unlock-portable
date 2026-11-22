# -*- coding: utf-8 -*-
"""
apply_patch.py —— 拖拽式「导入补丁包」核心：把破解补丁按目录结构覆盖进游戏目录。

跟 version_lock.py（锁版本，管"下哪个版本"）配对；这个只管"下完之后怎么覆盖补丁"。
安全设计：覆盖前把游戏目录里被替换的原文件备份到 _patch_backup/<appid>_<时间>/，可回滚。

用法（一般由 导入补丁包.bat 拖拽调用）：
  python apply_patch.py <appid> <补丁包.zip或目录> [--game-dir DIR] [--dry-run]
"""
import os, sys, re, shutil, zipfile, argparse, datetime

# 相对路径锚点：从这些目录段开始作为"游戏目录下的相对路径"
ANCHORS = {"ENGINE", "SB", "BINARIES", "CONTENT", "CONFIG", "PLUGINS", "BIN", "GAME"}


# ---------------------------------------------------------------- 定位游戏目录
def find_appmanifest(appid, roots=None):
    """在所有可能的 steamapps 目录里找 appmanifest_<appid>.acf。"""
    if roots is None:
        roots = []
        # 注册表 SteamPath
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            roots.append(os.path.join(winreg.QueryValueEx(k, "SteamPath")[0], "steamapps"))
        except Exception:
            pass
        # 常见库路径
        for drv in "CDEFGHIJK":
            for sub in ("SteamLibrary", "STEAM", "Steam", "SteamLibrary2"):
                roots.append(os.path.join(drv + ":\\", sub, "steamapps"))
    seen = set()
    for r in roots:
        r = os.path.normpath(r)
        if r.lower() in seen or not os.path.isdir(r):
            continue
        seen.add(r.lower())
        f = os.path.join(r, "appmanifest_%s.acf" % appid)
        if os.path.isfile(f):
            return f
    return None


def read_installdir(acf):
    """从 acf 读 installdir 字段。"""
    try:
        txt = open(acf, "r", encoding="utf-8", errors="replace").read()
    except Exception:
        return None
    m = re.search(r'"installdir"\s*"([^"]+)"', txt)
    return m.group(1) if m else None


def find_game_dir(appid, explicit=None):
    if explicit:
        return explicit
    acf = find_appmanifest(appid)
    if not acf:
        return None, "找不到 appmanifest_%s.acf（游戏可能还没入库/没下载）" % appid
    installdir = read_installdir(acf)
    if not installdir:
        return None, "acf 里没有 installdir 字段: %s" % acf
    game_dir = os.path.join(os.path.dirname(acf), "common", installdir)
    return game_dir, acf


# ---------------------------------------------------------------- 扫描补丁包
def collect_patch_files(path, tmp_root):
    """返回 [(相对游戏目录路径, 本地可读文件路径)]。zip 解压到 tmp_root。"""
    items = []

    def rel_of(full):
        parts = re.split(r"[\\/]", full.replace("/", "\\"))
        parts = [p for p in parts if p]
        # 找锚点，从锚点开始作为相对路径；找不到就去掉最外层包裹目录
        idx = None
        for i, seg in enumerate(parts):
            if seg.upper() in ANCHORS:
                idx = i
                break
        if idx is None:
            idx = 1 if len(parts) > 1 else 0
        return os.path.join(*parts[idx:])

    if os.path.isdir(path):
        for dp, _dn, fns in os.walk(path):
            for fn in fns:
                if fn.lower().endswith((".exe", ".dll", ".ini", ".txt", ".bat", ".cfg", ".json")):
                    full = os.path.join(dp, fn)
                    items.append((rel_of(full), full))
    elif os.path.isfile(path) and path.lower().endswith(".zip"):
        os.makedirs(tmp_root, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.endswith("/") or n.endswith("\\"):
                    continue
                if not n.lower().endswith((".exe", ".dll", ".ini", ".txt", ".bat", ".cfg", ".json")):
                    continue
                data = z.read(n)
                dst = os.path.join(tmp_root, os.path.basename(n))
                with open(dst, "wb") as f:
                    f.write(data)
                items.append((rel_of(n), dst))
    elif os.path.isfile(path):
        items.append((rel_of(path), path))
    return items


# ---------------------------------------------------------------- 覆盖（带备份）
def apply(appid, patch_path, game_dir, dry_run=False):
    tmp_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ap_unzip_tmp")
    items = collect_patch_files(patch_path, tmp_root)
    if not items:
        print("[错误] 补丁包里没找到 exe/dll/ini 等文件:", patch_path)
        return False

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = os.path.join(game_dir, "_patch_backup", "%s_%s" % (appid, ts))

    print("=" * 66)
    print("游戏目录:", game_dir)
    print("补丁包  :", patch_path)
    print("文件数  :", len(items))
    print("备份到  :", backup_root)
    if dry_run:
        print("[DRY-RUN] 仅预览，不实际覆盖")
    print("=" * 66)

    if not os.path.isdir(game_dir):
        print("[错误] 游戏目录不存在（游戏可能还没下完）:", game_dir)
        return False

    for rel, src in items:
        dst = os.path.join(game_dir, rel)
        exists = os.path.isfile(dst)
        print("  %s%s" % (rel, "  (原文件将备份)" if exists else "  (新文件)"))
        if dry_run:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if exists:
            bk = os.path.join(backup_root, rel)
            os.makedirs(os.path.dirname(bk), exist_ok=True)
            shutil.copy2(dst, bk)
        shutil.copy2(src, dst)

    # 清理临时解压
    if os.path.isdir(tmp_root):
        shutil.rmtree(tmp_root, ignore_errors=True)

    if not dry_run:
        print("=" * 66)
        print("[完成] 补丁已覆盖进游戏目录。原文件备份在:", backup_root)
        print("回滚方法：把备份目录里的文件按相同相对路径覆盖回去即可。")
    return True


def main():
    p = argparse.ArgumentParser(description="导入补丁包：按目录结构覆盖进游戏目录（带备份）")
    p.add_argument("appid", help="游戏 AppID")
    p.add_argument("patch", help="补丁包 zip 或目录")
    p.add_argument("--game-dir", help="手动指定游戏目录（默认自动定位）")
    p.add_argument("--dry-run", action="store_true", help="仅预览不覆盖")
    a = p.parse_args()

    gd, info = find_game_dir(a.appid, a.game_dir)
    if not gd:
        print("[错误]", info)
        sys.exit(1)
    if not a.game_dir:
        print("自动定位游戏目录:", info, "->", gd)

    # 安全检查：游戏是否下载完成
    if not os.path.isdir(gd) or not os.listdir(gd):
        print("[警告] 游戏目录为空或不存在——游戏可能还没下载完成。")
        print("       现在覆盖补丁会被后续下载冲掉。建议等下载完再执行。")
        ans = input("       仍要继续吗？(输入 yes 继续，其他退出): ").strip().lower()
        if ans != "yes":
            print("已退出，未做任何改动。")
            sys.exit(0)

    ok = apply(a.appid, a.patch, gd, dry_run=a.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
