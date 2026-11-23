import json
import os


def test_rollback_refuses_when_steam_running(monkeypatch, tmp_path):
    import backup as B
    monkeypatch.setattr(B, "steam_running", lambda: True)
    assert B.rollback(str(tmp_path)) is False


def test_rollback_aborts_on_manifest_hash_mismatch(monkeypatch, tmp_path):
    import backup as B
    monkeypatch.setattr(B, "steam_running", lambda: False)
    (tmp_path / "manifest.json").write_text(json.dumps([
        {"orig_path": str(tmp_path / "x.txt"), "sha256": "deadbeef", "size": 3, "file": "x.txt"}
    ]), encoding="utf-8")
    (tmp_path / "x.txt").write_text("tampered", encoding="utf-8")
    assert B.rollback(str(tmp_path)) is False


def test_snapshot_writes_manifest(monkeypatch, tmp_path):
    import backup as B
    src = tmp_path / "cfg.vdf"
    src.write_text("abc", encoding="utf-8")
    monkeypatch.setattr(B, "SNAPSHOT_ROOT", str(tmp_path / "snaps"))
    d = B.snapshot([str(src)], label="t")
    m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    assert m[0]["size"] == 3 and len(m[0]["sha256"]) == 64
