# -*- coding: utf-8 -*-
"""
网易云登录凭据提取器
从客户端内嵌 CEF（webapp91x64）的 Cookie 库中解出 MUSIC_U 等凭据，
落到独立副本目录，完全不依赖浏览器，也不会被 Edge 清理影响。

加密链路：
  LocalPrefs.json -> os_crypt.encrypted_key  (DPAPI 包裹的 32 字节 AES key)
  Cookies         -> encrypted_value          (v10 + AES-256-GCM)
"""
import os
import sys
import json
import glob
import time
import base64
import shutil
import sqlite3
import ctypes
import ctypes.wintypes as wt
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from Crypto.Cipher import AES

CLIENT_DIR = os.path.expandvars(r"%LOCALAPPDATA%\NetEase\CloudMusic")


def _find_cef_dir() -> str:
    """
    自动定位客户端的 CEF 配置目录（不同版本目录名不一样，
    例如 3.x 是 webapp91x64，旧版可能叫别的）。
    判据：同时存在 Cookies 和 LocalPrefs.json。
    """
    if os.path.isdir(CLIENT_DIR):
        for name in sorted(os.listdir(CLIENT_DIR)):
            d = os.path.join(CLIENT_DIR, name)
            if (os.path.isdir(d)
                    and os.path.exists(os.path.join(d, "Cookies"))
                    and os.path.exists(os.path.join(d, "LocalPrefs.json"))):
                return d
    return os.path.join(CLIENT_DIR, "webapp91x64")


CEF_DIR = _find_cef_dir()
COOKIE_DB = os.path.join(CEF_DIR, "Cookies")
LOCAL_PREFS = os.path.join(CEF_DIR, "LocalPrefs.json")

STORE_DIR = os.path.expandvars(r"%APPDATA%\ne-refresh")
CRED_FILE = os.path.join(STORE_DIR, "cred.json")
SNAP_DIR = os.path.join(STORE_DIR, "snapshots")
KEEP_SNAPSHOTS = 10

# 需要保留的凭据键
TARGETS = (
    "MUSIC_U", "MUSIC_A_T", "MUSIC_R_T", "__csrf",
    "deviceId", "os", "appver", "osver", "channel", "NMTID",
)


# --------------------------------------------------------------------------
# DPAPI
# --------------------------------------------------------------------------
class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_unprotect(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise RuntimeError("CryptUnprotectData 失败（可能换了用户或机器）")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _os_crypt_key() -> bytes:
    if not os.path.exists(LOCAL_PREFS):
        raise FileNotFoundError(f"找不到 {LOCAL_PREFS}，客户端可能未安装或未运行过")
    prefs = json.load(open(LOCAL_PREFS, encoding="utf-8"))
    ek = base64.b64decode(prefs["os_crypt"]["encrypted_key"])
    if ek[:5] == b"DPAPI":
        ek = ek[5:]
    key = _dpapi_unprotect(ek)
    if len(key) != 32:
        raise RuntimeError(f"AES key 长度异常: {len(key)}")
    return key


def _decrypt_value(key: bytes, enc: bytes) -> str:
    if enc[:3] == b"v10":
        blob = enc[3:]
        nonce, body = blob[:12], blob[12:]
        ct, tag = body[:-16], body[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag).decode("utf-8", "replace")
    if enc[:3] == b"v20":
        raise RuntimeError("v20 (App-Bound) 加密，当前机器不需要，请反馈")
    # 老格式：整段 DPAPI
    return _dpapi_unprotect(enc).decode("utf-8", "replace")


# --------------------------------------------------------------------------
# 读取客户端 Cookie
# --------------------------------------------------------------------------
def read_client_cookies() -> dict:
    """从客户端 Cookies 库解出凭据字典（全量，同名取第一条）"""
    full = read_client_cookies_full()
    out = {}
    for c in full:
        out.setdefault(c["name"], c["value"])
    if not out.get("MUSIC_U"):
        raise RuntimeError("没解出 MUSIC_U —— 客户端未登录，或加密格式变了")
    return out


def read_client_cookies_full():
    """返回 [{name,value,domain,path}]，用于往浏览器里全量注入（含 JSESSIONID 等会话 cookie）"""
    if not os.path.exists(COOKIE_DB):
        raise FileNotFoundError(f"找不到 {COOKIE_DB}")

    tmp = os.path.join(tempfile.gettempdir(), f"nerefresh_{os.getpid()}_{int(time.time())}.db")
    shutil.copy2(COOKIE_DB, tmp)  # 客户端可能锁着库，复制后读
    try:
        con = sqlite3.connect(tmp)
        try:
            rows = con.execute(
                "select host_key, name, encrypted_value from cookies "
                "where (host_key like '%music.163.com%' or host_key like '%163.com%') "
                "and encrypted_value is not null"
            ).fetchall()
        finally:
            con.close()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    key = _os_crypt_key()
    out, seen = [], set()
    for host, name, enc in rows:
        if (host, name) in seen:
            continue
        seen.add((host, name))
        try:
            val = _decrypt_value(key, enc)
        except Exception:
            continue
        if not val:
            continue
        out.append({"name": name, "value": val, "domain": host, "path": "/"})

    if not any(c["name"] == "MUSIC_U" for c in out):
        raise RuntimeError("没解出 MUSIC_U —— 客户端未登录，或加密格式变了")
    return out


# --------------------------------------------------------------------------
# 副本存取
# --------------------------------------------------------------------------
def save_cred(cookies: dict) -> str:
    os.makedirs(SNAP_DIR, exist_ok=True)
    payload = {"saved_at": int(time.time()), "cookies": cookies}
    with open(CRED_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    snap = os.path.join(SNAP_DIR, f"cred_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(snap, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    snaps = sorted(glob.glob(os.path.join(SNAP_DIR, "cred_*.json")))
    for old in snaps[:-KEEP_SNAPSHOTS]:
        try:
            os.remove(old)
        except OSError:
            pass
    return snap


def load_cred():
    """返回 (cookies, saved_at) 或 (None, None)"""
    if not os.path.exists(CRED_FILE):
        return None, None
    try:
        d = json.load(open(CRED_FILE, encoding="utf-8"))
        return d.get("cookies"), d.get("saved_at")
    except Exception:
        return None, None


def export_from_client() -> dict:
    """强制从客户端重新解一次并落盘（含 __full__ 全量列表供浏览器注入）"""
    full = read_client_cookies_full()
    cookies = {}
    for c in full:
        cookies.setdefault(c["name"], c["value"])
    cookies["__full__"] = full
    save_cred(cookies)
    return cookies


def get_cred(max_age_hours: float = 12.0, force: bool = False) -> dict:
    """
    拿一份可用凭据：
      1) 副本够新就直接用
      2) 否则回客户端重解
      3) 客户端也解不出来，才退回旧副本
    """
    if not force:
        c, ts = load_cred()
        if c and c.get("MUSIC_U") and ts and (time.time() - ts) < max_age_hours * 3600:
            return c
    try:
        return export_from_client()
    except Exception as e:
        c, _ = load_cred()
        if c and c.get("MUSIC_U"):
            print(f"[warn] 回客户端重解失败({e})，使用旧副本", file=sys.stderr)
            return c
        raise


def cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items()
                     if v and k != "__full__")


if __name__ == "__main__":
    cs = get_cred(force=True)
    print("已导出凭据：")
    for k in TARGETS:
        v = cs.get(k)
        if v:
            shown = v if len(v) <= 10 else v[:5] + "***" + v[-3:]
            print(f"  {k:<10} len={len(v):<5} {shown}")
    print("副本：", CRED_FILE)
