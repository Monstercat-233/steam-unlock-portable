def test_format_judge_string_tuple():
    from main_app import format_judge
    s = format_judge((True, "需票据/补丁", "单机无需", "有 Denuvo"))
    assert "下载" in s and "运行" in s and "联机" in s


def test_account_label():
    from main_app import account_label
    assert "monstercaatt" in account_label({"account_name": "monstercaatt", "accountid": 1230565209})


def test_pick_patch_file_returns_single_file(monkeypatch):
    import main_app
    b = main_app.Bridge.__new__(main_app.Bridge)
    monkeypatch.setattr(b, "_pick_path", lambda dialog="open", title="": r"D:\pack\lock.lua")
    assert b.pick_patch_file() == {"ok": True, "data": r"D:\pack\lock.lua", "error": ""}


def test_set_online_mode_blocks_third_party(monkeypatch):
    """自有账号/反作弊游戏应被硬拦，不关 Steam 不改文件。"""
    import main_app
    b = main_app.Bridge.__new__(main_app.Bridge)
    b._accounts = [{"accountid": 732831206, "account_name": "smallmonstercat"}]
    monkeypatch.setattr(main_app.AA, "fetch_app_info", lambda a: {
        "name": "EA 游戏", "drm": "", "third_party_account": True,
        "vac": False, "has_key": True, "depots": {"1": "x"}})
    calls = []
    monkeypatch.setattr(main_app.P, "stop_steam", lambda: calls.append("stop") or {})
    monkeypatch.setattr(main_app.P, "start_steam", lambda s: calls.append("start") or {})
    r = b.set_online_mode("999", 0, True)
    assert r["ok"] is False
    assert "自有账号" in r["error"]
    assert calls == []  # 根本没动 Steam


def test_online_status_readonly(monkeypatch):
    import main_app
    b = main_app.Bridge.__new__(main_app.Bridge)
    b._accounts = [{"accountid": 732831206, "account_name": "smallmonstercat"}]
    monkeypatch.setattr(main_app.AA, "fetch_app_info", lambda a: {
        "name": "测试游戏", "drm": "", "third_party_account": False,
        "vac": False, "has_key": True, "depots": {"1": "x"}})
    monkeypatch.setattr(main_app.OM, "read_online_flag", lambda aid, appid: {
        "ok": True, "enabled": False, "value": "-dx12", "error": ""})
    r = b.online_status("3489700", 0)
    assert r["ok"] is True
    assert r["data"]["classify"]["level"] == "ok"
    assert r["data"]["launch_value"] == "-dx12"
    assert r["data"]["enabled"] is False


def test_pick_path_file_types_are_valid_for_pywebview():
    """_pick_path 传给 webview 的 file_types 必须能被 pywebview 解析，
    否则 create_file_dialog 抛 ValueError，文件对话框打不开（2026-11-26 bug）。"""
    import main_app
    from webview.util import parse_file_type
    b = main_app.Bridge.__new__(main_app.Bridge)
    captured = {}

    class FakeWindow:
        def create_file_dialog(self, kind, allow_multiple=False, file_types=None):
            captured["file_types"] = file_types
            return []

    b._window = FakeWindow()
    b._pick_path(dialog="open", title="test")
    fts = captured.get("file_types") or ()
    assert fts, "open 对话框应传 file_types"
    for ft in fts:
        parse_file_type(ft)  # 非法格式会抛 ValueError 令测试失败
