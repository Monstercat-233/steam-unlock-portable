"""联机模式：-onlinefix 启动选项的精确增删 + 游戏分类 + 安全校验。"""
import copy


_SAMPLE = '''"UserLocalConfigStore"
{
\t"Software"
\t{
\t\t"Valve"
\t\t{
\t\t\t"Steam"
\t\t\t{
\t\t\t\t"apps"
\t\t\t\t{
\t\t\t\t\t"1091500"
\t\t\t\t\t{
\t\t\t\t\t\t"LaunchOptions"\t\t"-dx12"
\t\t\t\t\t}
\t\t\t\t\t"3489700"
\t\t\t\t\t{
\t\t\t\t\t\t"Playtime"\t\t"100"
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
\t}
}
'''


# ---------- 分类判定 ----------

def test_classify_third_party_blocked():
    import online_mode as OM
    r = OM.classify(999, {"drm": "", "third_party_account": True, "vac": False,
                          "has_key": True, "depots": {"999": "x"}})
    assert r["level"] == "blocked"
    assert "自有账号" in r["reason"] or "EA" in r["reason"] or "Ubisoft" in r["reason"]


def test_classify_vac_warn():
    import online_mode as OM
    r = OM.classify(999, {"drm": "", "third_party_account": False, "vac": True,
                          "has_key": True, "depots": {"999": "x"}})
    assert r["level"] == "warn"
    assert "VAC" in r["reason"]


def test_classify_denuvo_singleplayer_na():
    import online_mode as OM
    r = OM.classify(999, {"drm": "Denuvo Anti-Tamper", "third_party_account": False,
                          "vac": False, "has_key": True, "depots": {"999": "x"}})
    assert r["level"] == "na"


def test_classify_steamworks_ok():
    import online_mode as OM
    r = OM.classify(999, {"drm": "", "third_party_account": False, "vac": False,
                          "has_key": True, "depots": {"999": "x"}})
    assert r["level"] == "ok"


def test_classify_no_key_na():
    import online_mode as OM
    r = OM.classify(999, {"drm": "", "third_party_account": False, "vac": False,
                          "has_key": False, "depots": {}})
    assert r["level"] == "na"


# ---------- VDF 精确修改 ----------

def test_enable_appends_to_existing_option():
    import online_mode as OM
    new, info = OM.modify_launch_options(_SAMPLE, "1091500", True)
    assert "-dx12" in new and "-onlinefix" in new
    assert info["changed"] is True
    assert info["new_value"] == "-dx12 -onlinefix"
    assert info["old_value"] == "-dx12"


def test_disable_keeps_other_options():
    import online_mode as OM
    s = _SAMPLE.replace('"-dx12"', '"-dx12 -onlinefix"')
    new, info = OM.modify_launch_options(s, "1091500", False)
    assert '"-dx12"' in new
    assert "onlinefix" not in new
    assert info["new_value"] == "-dx12"


def test_enable_inserts_when_no_launchoptions():
    import online_mode as OM
    new, info = OM.modify_launch_options(_SAMPLE, "3489700", True)
    assert info["changed"] is True and info["inserted"] is True
    assert "-onlinefix" in new
    # 只在该 appid 块内插入
    assert '"-dx12"' in new


def test_enable_is_idempotent():
    import online_mode as OM
    once, _ = OM.modify_launch_options(_SAMPLE, "1091500", True)
    twice, info = OM.modify_launch_options(once, "1091500", True)
    assert twice == once
    assert info["changed"] is False
    assert twice.count("-onlinefix") == 1


def test_only_target_field_changes():
    """完整性：把改后的 value 换回原值，必须与原文逐字节一致。"""
    import online_mode as OM
    new, info = OM.modify_launch_options(_SAMPLE, "1091500", True)
    restored = new.replace('"-dx12 -onlinefix"', '"-dx12"', 1)
    assert restored == _SAMPLE


def test_missing_appid_raises():
    import online_mode as OM
    import pytest
    with pytest.raises(ValueError):
        OM.modify_launch_options(_SAMPLE, "9999999", True)


# ---------- 文件级：备份 + 只动目标文件 ----------

def test_set_online_flag_backs_up_and_writes(tmp_path, monkeypatch):
    import online_mode as OM
    steam = tmp_path / "steam"
    lc = steam / "userdata" / "732831206" / "config"
    lc.mkdir(parents=True)
    (lc / "localconfig.vdf").write_text(_SAMPLE, encoding="utf-8")
    writable = tmp_path / "writable"
    writable.mkdir()

    monkeypatch.setattr(OM.P, "find_steam_dir", lambda: str(steam))
    monkeypatch.setattr(OM.P, "writable_dir", lambda: str(writable))

    r = OM.set_online_flag("732831206", "1091500", True)
    assert r["changed"] is True
    assert "-onlinefix" in (lc / "localconfig.vdf").read_text(encoding="utf-8")
    assert r["backup"] and __import__("os").path.exists(r["backup"])


def test_set_online_flag_dry_run_no_write(tmp_path, monkeypatch):
    import online_mode as OM
    steam = tmp_path / "steam"
    lc = steam / "userdata" / "732831206" / "config"
    lc.mkdir(parents=True)
    target = lc / "localconfig.vdf"
    target.write_text(_SAMPLE, encoding="utf-8")
    writable = tmp_path / "writable"
    writable.mkdir()
    monkeypatch.setattr(OM.P, "find_steam_dir", lambda: str(steam))
    monkeypatch.setattr(OM.P, "writable_dir", lambda: str(writable))

    r = OM.set_online_flag("732831206", "1091500", True, dry_run=True)
    assert r["changed"] is True
    assert target.read_text(encoding="utf-8") == _SAMPLE  # 没写盘
