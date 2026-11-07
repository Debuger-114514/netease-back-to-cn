# -*- coding: utf-8 -*-
"""
状态探针：抽样热歌榜，统计"能否拿到播放地址"的通过率
通过率≈账号当前的国内授权状态是否健在。
"""
import os
import sys
import json
import time
import random
import hashlib
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

import cred

EAPI_KEY = b"e82ckenh8dichen8"
MAGIC = "36cd479b6b5"
REAL_IP = os.environ.get("NE_REAL_IP", "211.161.244.70")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TOPLIST_ID = 3778678   # 云音乐热歌榜


def _eapi(path, obj):
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.md5(f"nobody{path}use{text}md5forencrypt".encode()).hexdigest()
    raw = f"{path}-{MAGIC}-{text}-{MAGIC}-{digest}"
    return AES.new(EAPI_KEY, AES.MODE_ECB).encrypt(pad(raw.encode(), 16)).hex().upper()


def _post(path, body, cookie):
    req = urllib.request.Request(
        "https://music.163.com" + path, data=body.encode(),
        headers={
            "User-Agent": UA, "Referer": "https://music.163.com/",
            "Origin": "https://music.163.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": cookie, "X-Real-IP": REAL_IP,
        }, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def _get(path, cookie):
    req = urllib.request.Request(
        "https://music.163.com" + path,
        headers={"User-Agent": UA, "Referer": "https://music.163.com/",
                 "Cookie": cookie, "X-Real-IP": REAL_IP})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def sample_ids(n=20):
    """取热歌榜歌曲 id"""
    cookie = cred.cookie_header(cred.get_cred())
    d = _get(f"/api/v3/playlist/detail?id={TOPLIST_ID}&n=1000", cookie)
    tracks = ((d.get("playlist") or {}).get("tracks")) or []
    ids = [t["id"] for t in tracks if (t.get("fee") or 0) != 1]  # 跳过纯 VIP 歌
    if not ids:
        raise RuntimeError("拿不到热歌榜，接口可能变了")
    random.shuffle(ids)
    return ids[:n]


def check(n=20) -> dict:
    """返回 {rate, total, ok, ids, error}"""
    res = {"ok": 0, "total": 0, "rate": 0.0, "failed_ids": [], "error": None,
           "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        cookie = cred.cookie_header(cred.get_cred())
        ids = sample_ids(n)
        res["total"] = len(ids)
        for sid in ids:
            try:
                body = _post("/eapi/song/enhance/player/url",
                             f"params={_eapi('/api/song/enhance/player/url', {'ids': f'[{sid}]', 'br': 320000, 'e_r': False})}",
                             cookie)
                data = (json.loads(body).get("data") or [{}])[0]
                if data.get("url"):
                    res["ok"] += 1
                else:
                    res["failed_ids"].append(sid)
            except Exception:
                res["failed_ids"].append(sid)
            time.sleep(0.4)
        res["rate"] = round(res["ok"] / res["total"], 3) if res["total"] else 0.0
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return res


if __name__ == "__main__":
    r = check(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
    print(json.dumps(r, ensure_ascii=False, indent=1))
