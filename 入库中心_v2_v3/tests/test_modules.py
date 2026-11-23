import os


SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def test_upsert_idempotent(tmp_path, monkeypatch):
    import version_lock as V
    lua = tmp_path / "mygames.lua"
    lua.write_text("", encoding="utf-8")
    monkeypatch.setattr(V, "LUA_PATH", str(lua))
    info = {"name": "T", "depots": {"3489700": "a" * 64}, "manifest": {}, "drm": "Denuvo"}
    for _ in range(3):
        V.upsert_lock_block(3489700, "T", {"3489701": "2747626496734343426"}, info)
    txt = lua.read_text(encoding="utf-8")
    assert txt.count("-- #OSTBLOCK:3489700") == 1
    assert 'setManifestid(3489701, "2747626496734343426")' in txt


def test_build_block_uses_numeric_manifestid():
    import auto_adapt as AA
    info = {"name": "T", "depots": {"550": "a" * 64}, "manifest": {"550": "12345"}, "drm": ""}
    blk = AA.build_block(550, info=info)
    assert 'setManifestid(550, "12345")' in blk
    assert 'setManifestid("550"' not in blk


def test_no_hardcoded_steam_path_in_sources():
    for name in ("auto_adapt.py", "version_lock.py", "denuvo_helper.py"):
        text = open(os.path.join(SRC, name), encoding="utf-8").read()
        assert r"D:\STEAM" not in text, name


def test_get_key_db_no_download_when_missing(tmp_path, monkeypatch):
    import auto_adapt as AA
    monkeypatch.setattr(AA, "MASTER_KEYS_PATH", str(tmp_path / "none.json"))
    monkeypatch.setattr(AA, "_key_db", None)  # 模拟冷启动
    def boom(force=False):
        raise AssertionError("should not download")
    monkeypatch.setattr(AA, "refresh_master_keys", boom)
    assert AA.get_key_db() == {}
