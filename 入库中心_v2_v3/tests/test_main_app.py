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
