"""一键冷启动：clear_appinfo 备份+删除 + cold_restart 编排。"""
import os


def test_clear_appinfo_backs_up_and_removes(tmp_path, monkeypatch):
    import paths as P
    steam = tmp_path / "Steam"
    appcache = steam / "appcache"
    appcache.mkdir(parents=True)
    vdf = appcache / "appinfo.vdf"
    vdf.write_bytes(b"DATA")
    idir = appcache / "appinfo"
    idir.mkdir()
    (idir / "x.bin").write_bytes(b"x")
    backup = tmp_path / "backup"

    monkeypatch.setattr(P, "writable_dir", lambda: str(backup))

    r = P.clear_appinfo(str(steam))
    assert r["removed"] is True
    assert not vdf.exists()
    assert not idir.exists()
    assert r["backup_path"]
    assert os.path.exists(r["backup_path"])


def test_clear_appinfo_noop_when_missing(tmp_path, monkeypatch):
    import paths as P
    steam = tmp_path / "Steam"
    steam.mkdir()
    monkeypatch.setattr(P, "writable_dir", lambda: str(tmp_path / "backup"))
    r = P.clear_appinfo(str(steam))
    assert r["removed"] is False
    assert r["backup_path"] == ""


def test_cold_restart_api(monkeypatch):
    import main_app
    b = main_app.Bridge.__new__(main_app.Bridge)
    calls = []
    monkeypatch.setattr(main_app.P, "find_steam_dir", lambda: r"D:\Steam")
    monkeypatch.setattr(main_app.P, "stop_steam", lambda: calls.append("stop") or {"killed": ["steam.exe"]})
    monkeypatch.setattr(main_app.P, "clear_appinfo", lambda s: calls.append("clear") or {"removed": True, "backup_path": "bk"})
    monkeypatch.setattr(main_app.UG, "reset_auto_update", lambda: calls.append("reset") or {"changed": ["3489700"], "backups": {}})
    monkeypatch.setattr(main_app.P, "start_steam", lambda s: calls.append("start") or {"started": True, "pid": 1})

    r = b.cold_restart()
    assert calls == ["stop", "reset", "clear", "start"]
    assert r["ok"] is True
    assert r["data"]["steam_dir"] == r"D:\Steam"
    assert r["data"]["reset"]["changed"] == ["3489700"]
