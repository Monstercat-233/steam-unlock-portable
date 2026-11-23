def test_local_substring_match(monkeypatch, tmp_path):
    import game_index as G
    monkeypatch.setattr(G, "NAMES_PATH", str(tmp_path / "names.json"))
    (tmp_path / "names.json").write_text('{"3489700":"StellarBlade"}', encoding="utf-8")
    assert (3489700, "StellarBlade") in G.search("Stellar")


def test_network_failure_returns_empty(monkeypatch, tmp_path):
    import game_index as G
    monkeypatch.setattr(G, "NAMES_PATH", str(tmp_path / "names.json"))
    (tmp_path / "names.json").write_text("{}", encoding="utf-8")
    def boom(q):
        raise Exception("offline")
    monkeypatch.setattr(G, "_storesearch", boom)
    assert G.search("某不存在的游戏") == []


def test_add_name_persists(monkeypatch, tmp_path):
    import game_index as G
    monkeypatch.setattr(G, "NAMES_PATH", str(tmp_path / "names.json"))
    (tmp_path / "names.json").write_text("{}", encoding="utf-8")
    G.add_name(550, "Left 4 Dead 2")
    assert G.load_names()["550"] == "Left 4 Dead 2"
