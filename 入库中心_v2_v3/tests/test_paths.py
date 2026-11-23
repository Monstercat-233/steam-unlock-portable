import sys


def test_accountid_from_steam64():
    from paths import steam64_to_accountid
    assert steam64_to_accountid(76561199190830937) == 1230565209


def test_lua_path_uses_find_steam_dir(monkeypatch):
    import paths
    monkeypatch.setattr(paths, "find_steam_dir", lambda: r"D:\fake\Steam")
    assert paths.lua_path() == r"D:\fake\Steam\config\stplug-in\mygames.lua"


def test_resource_vs_writable_dirs_are_distinct_when_frozen(monkeypatch):
    import paths
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", r"D:\tmp\_MEIxxxx", raising=False)
    monkeypatch.setattr(sys, "executable", r"D:\STEAM入库\全自动入库_v2\入库中心.exe", raising=False)
    assert paths.resource_dir() == r"D:\tmp\_MEIxxxx"
    assert paths.writable_dir() == r"D:\STEAM入库\全自动入库_v2"


def test_find_steam_dir_explicit_wins(monkeypatch):
    import paths
    monkeypatch.delenv("STEAM_PATH", raising=False)
    monkeypatch.setattr(paths, "_reg_steam_path", lambda: None)
    monkeypatch.setattr(paths, "_process_steam_path", lambda: None)
    monkeypatch.setattr(paths, "_common_steam_dirs", lambda: [])
    assert paths.find_steam_dir(r"X:\explicit") == r"X:\explicit"


def test_find_steam_dir_from_env(monkeypatch):
    import paths
    monkeypatch.setenv("STEAM_PATH", r"E:\EnvSteam")
    assert paths.find_steam_dir() == r"E:\EnvSteam"


def test_list_accounts_parses_vdf(monkeypatch, tmp_path):
    import paths
    steam = tmp_path / "steam"
    cfg = steam / "config"
    cfg.mkdir(parents=True)
    (cfg / "loginusers.vdf").write_text(
        '"users"\n{\n'
        '  "76561199190830937"\n  {\n'
        '    "AccountName"  "monstercaatt"\n'
        '    "PersonaName"  "星痕"\n'
        '  }\n}\n', encoding="utf-8")
    monkeypatch.setattr(paths, "find_steam_dir", lambda: str(steam))
    accs = paths.list_accounts()
    assert len(accs) == 1
    assert accs[0]["accountid"] == 1230565209
    assert accs[0]["account_name"] == "monstercaatt"


def test_current_account_matches_autologinuser(monkeypatch):
    import paths
    monkeypatch.setattr(paths, "_reg_autologinuser", lambda: "monstercaatt")
    monkeypatch.setattr(paths, "list_accounts", lambda: [
        {"accountid": 1, "account_name": "other"},
        {"accountid": 1230565209, "account_name": "monstercaatt"},
    ])
    acc = paths.current_account()
    assert acc["accountid"] == 1230565209


def test_current_account_none_when_no_match(monkeypatch):
    import paths
    monkeypatch.setattr(paths, "_reg_autologinuser", lambda: "ghost")
    monkeypatch.setattr(paths, "list_accounts", lambda: [])
    assert paths.current_account() is None
