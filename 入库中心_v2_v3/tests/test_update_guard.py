"""update_guard 启动自检：自动更新预约（AutoUpdateBehavior）判据。"""
import copy


_FAKE_ACF = '''"AppState"
{
\t"appid"  "3489700"
\t"buildid"  "26123051"
\t"TargetBuildID"  "26123051"
\t"AutoUpdateBehavior"  "1"
\t"ScheduledAutoUpdate"  "1795616720"
\t"InstalledDepots"
\t{
\t\t"3489701"
\t\t{
\t\t\t"manifest"  "2747626496734343426"
\t\t}
\t}
}
'''

_LOCKED = {
    "3489700": {
        "verified": True,
        "name": "剑星",
        "locked_gids": {"3489701": "2747626496734343426"},
    }
}

_BASE = {
    "3489700": {
        "buildid": "26123051",
        "target_buildid": "26123051",
        "manifest_gids": {"3489701": "2747626496734343426"},
        "captured_at": "2026-11-25T00:00:00",
    }
}

_CURRENT = {
    "buildid": "26123051",
    "target_buildid": "26123051",
    "install_dir": "StellarBlade",
    "manifest_gids": {"3489701": "2747626496734343426"},
    "auto_update_behavior": "0",
    "scheduled_auto_update": "0",
}


def test_read_acf_parses_auto_update_fields(monkeypatch):
    import update_guard as UG

    monkeypatch.setattr(UG, "_read_text", lambda p: _FAKE_ACF)
    got = UG.read_acf(3489700, dirs=["X"])
    assert got["auto_update_behavior"] == "1"
    assert got["scheduled_auto_update"] == "1795616720"


def _patch(monkeypatch, current):
    import update_guard as UG

    monkeypatch.setattr(UG, "read_acf", lambda appid, dirs=None: copy.deepcopy(current))
    monkeypatch.setattr(UG, "locked_apps", lambda: copy.deepcopy(_LOCKED))
    monkeypatch.setattr(UG, "_load_baseline", lambda: copy.deepcopy(_BASE))
    return UG


def test_check_updates_flags_auto_update_enabled(monkeypatch):
    """buildid/GID 全对，仅 AutoUpdateBehavior=1 也必须报。"""
    UG = _patch(monkeypatch, dict(_CURRENT, auto_update_behavior="1",
                                 scheduled_auto_update="1795616720"))
    items = UG.check_updates()
    assert len(items) == 1, items
    reasons = " ".join(items[0]["reasons"])
    assert "自动更新" in reasons, reasons
    assert "停 Steam" in reasons or "停止 Steam" in reasons, reasons


def test_check_updates_flags_scheduled_only(monkeypatch):
    """AutoUpdateBehavior=0 但 ScheduledAutoUpdate 非 0 也要报。"""
    UG = _patch(monkeypatch, dict(_CURRENT, auto_update_behavior="0",
                                 scheduled_auto_update="1795616720"))
    items = UG.check_updates()
    assert len(items) == 1, items
    assert "自动更新" in " ".join(items[0]["reasons"])


def test_check_updates_ignores_auto_update_disabled(monkeypatch):
    """两个字段全 0 → 无告警。"""
    UG = _patch(monkeypatch, dict(_CURRENT))
    assert UG.check_updates() == []


def test_format_report_mentions_fix(monkeypatch):
    UG = _patch(monkeypatch, dict(_CURRENT, auto_update_behavior="1",
                                 scheduled_auto_update="1795616720"))
    report = UG.format_report(UG.check_updates())
    assert "AutoUpdateBehavior" in report
    assert "ScheduledAutoUpdate" in report
