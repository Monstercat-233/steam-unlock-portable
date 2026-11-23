# -*- coding: utf-8 -*-
"""游戏名本地索引：模糊匹配 names.json，未命中再联网 storesearch 补查并写回缓存。"""
import os
import json
import urllib.request
import urllib.parse

import paths as P
import auto_adapt as AA

NAMES_PATH = os.path.join(P.writable_dir(), "names.json")


def load_names():
    if os.path.isfile(NAMES_PATH):
        try:
            d = json.load(open(NAMES_PATH, "r", encoding="utf-8"))
            return {str(k): v for k, v in d.items()}
        except Exception:
            pass
    return {}


def _storesearch(q):
    url = AA.STORESEARCH.format(q=urllib.parse.quote(q))
    req = urllib.request.Request(url, headers=AA.UA)
    with urllib.request.urlopen(req, timeout=5) as r:
        data = r.read()
    items = json.loads(data.decode("utf-8", "replace")).get("items") or []
    return [(int(it["id"]), it.get("name") or q) for it in items if it.get("id")]


def search(q):
    q = str(q).strip()
    if not q:
        return []
    names = load_names()
    out = []
    ql = q.lower()
    for appid, name in names.items():
        if ql in str(name).lower() or str(appid).startswith(q):
            out.append((int(appid), name))
            if len(out) >= 20:
                break
    if out:
        return out
    try:
        found = _storesearch(q)
        for appid, name in found:
            add_name(appid, name)
        return found[:20]
    except Exception:
        return []


def add_name(appid, name):
    names = load_names()
    names[str(int(appid))] = name
    try:
        os.makedirs(os.path.dirname(NAMES_PATH), exist_ok=True)
        with open(NAMES_PATH, "w", encoding="utf-8") as f:
            json.dump(names, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
