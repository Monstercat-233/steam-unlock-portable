"""破解包路径导入：analyze_pack 纯识别逻辑 + import_crackpack 路径优先。"""


def test_analyze_pack_single_lua_extracts_appid_and_gids(tmp_path):
    import version_lock as V
    lua = tmp_path / "3489700.lua"
    lua.write_text(
        'addappid(3489700, 1, "' + "a" * 64 + '")\n'
        'addappid(3489701, 1, "' + "b" * 64 + '")\n'
        'setManifestid(3489701, "2747626496734343426")\n'
        'setManifestid(3596180, "8344797041293440177")\n',
        encoding="utf-8",
    )
    r = V.analyze_pack(str(lua))
    assert r["appid"] == 3489700
    assert r["gids"] == {
        "3489701": "2747626496734343426",
        "3596180": "8344797041293440177",
    }
    assert r["lua_count"] == 1
    assert r["patch_files"] == []


def test_analyze_pack_directory_counts_patch_files(tmp_path):
    import version_lock as V
    (tmp_path / "lock.lua").write_text(
        'addappid(4115450)\nsetManifestid(4115451, "999")\n', encoding="utf-8"
    )
    (tmp_path / "game.exe").write_bytes(b"MZ")
    (tmp_path / "api.dll").write_bytes(b"MZ")
    r = V.analyze_pack(str(tmp_path))
    assert r["appid"] == 4115450
    assert r["gids"] == {"4115451": "999"}
    assert len(r["patch_files"]) == 2


def test_analyze_pack_no_gids_returns_empty(tmp_path):
    import version_lock as V
    lua = tmp_path / "plain.lua"
    lua.write_text("addappid(3489700)\n", encoding="utf-8")
    r = V.analyze_pack(str(lua))
    assert r["appid"] == 3489700
    assert r["gids"] == {}


def test_import_crackpack_uses_passed_path(monkeypatch):
    import main_app
    b = main_app.Bridge.__new__(main_app.Bridge)
    seen = {}

    def fake_analyze(path):
        seen["path"] = path
        return {
            "appid": 3489700,
            "gids": {"3489701": "123"},
            "patch_files": [],
            "lua_count": 1,
        }

    monkeypatch.setattr(main_app.V, "analyze_pack", fake_analyze)
    monkeypatch.setattr(main_app.AA, "fetch_app_info", lambda aid: {"name": "SB"})
    monkeypatch.setattr(main_app.V, "upsert_lock_block", lambda *a, **k: "blk")
    monkeypatch.setattr(main_app.V, "stage_patch", lambda *a, **k: [])
    monkeypatch.setattr(main_app.V, "load_library", lambda: {})
    monkeypatch.setattr(main_app.V, "save_library", lambda x: None)
    monkeypatch.setattr(main_app.B, "audit", lambda *a, **k: None)
    monkeypatch.setattr(b, "_locklib", lambda: {})
    monkeypatch.setattr(b, "_library", lambda: {})

    r = b.import_crackpack(path=r"D:\pack.lua")
    assert seen["path"] == r"D:\pack.lua"
    assert r["ok"] is True
