# -*- coding: utf-8 -*-
"""
入口：刷新 + 体检 + 记账
设计目标是被任务计划以 pythonw 无窗口调用，所以所有输出都落文件。
"""
import os
import sys
import json
import time

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "run.log")
JSONL = os.path.join(LOG_DIR, "history.jsonl")
ALERT = os.path.join(LOG_DIR, "ALERT.txt")

class _Tee:
    """同时写日志文件和控制台；pythonw 下控制台为 None 也不报错"""
    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass

    def reconfigure(self, *a, **k):
        for st in self.streams:
            if hasattr(st, "reconfigure"):
                try:
                    st.reconfigure(*a, **k)
                except Exception:
                    pass

    def isatty(self):
        return False


_log_handle = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
sys.stdout = _Tee(_log_handle, sys.stdout)
sys.stderr = _Tee(_log_handle, sys.stderr)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, BASE)
import cred      # noqa: E402
import refresh   # noqa: E402
import monitor   # noqa: E402

THRESHOLD = float(os.environ.get("NE_THRESHOLD", "0.85"))
SAMPLE = int(os.environ.get("NE_SAMPLE", "20"))
PLAY_SONG = int(os.environ.get("NE_PLAY_SONG", "0")) or None


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)


def notify_fail(reason):
    """失败留痕：写 ALERT + 桌面通知文件"""
    try:
        with open(ALERT, "w", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{reason}\n")
        desk = os.path.join(os.path.expanduser("~"), "Desktop")
        target = os.path.join(desk, "网易云刷新失败.txt") if os.path.isdir(desk) else ALERT
        with open(target, "w", encoding="utf-8") as f:
            f.write(f"网易云国内授权刷新失败\n\n时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"原因：{reason}\n\n排查：查看 {LOG_FILE}\n")
    except Exception:
        pass


def clear_alert():
    for p in (ALERT, os.path.join(os.path.expanduser("~"), "Desktop", "网易云刷新失败.txt")):
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def append_history(rec):
    try:
        with open(JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    t0 = time.time()
    rec = {"ts": int(t0), "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    log("=" * 58)
    log("开始一轮")

    # 1. 凭据
    try:
        cs = cred.get_cred()
        age = None
        _, saved = cred.load_cred()
        if saved:
            age = round((time.time() - saved) / 3600, 1)
        log(f"凭据 OK  MUSIC_U={len(cs.get('MUSIC_U',''))}字  "
            f"副本年龄={age if age is not None else '?'}h")
        rec["cred"] = "ok"
    except Exception as e:
        log(f"凭据 FAIL: {e}")
        rec["cred"] = f"fail: {e}"
        rec["result"] = "fail"
        append_history(rec)
        notify_fail(f"凭据提取失败：{e}")
        return 1

    # 2. 刷新前状态
    pre = monitor.check(SAMPLE)
    log(f"刷新前可播率 {pre['ok']}/{pre['total']} = {pre['rate']:.0%}"
        + (f"  (err={pre['error']})" if pre["error"] else ""))
    rec["pre"] = {"rate": pre["rate"], "ok": pre["ok"], "total": pre["total"]}

    # 3. 刷新（每轮自动选一首热歌榜的歌来“播放”，复现手工流程）
    global PLAY_SONG
    if PLAY_SONG is None:
        try:
            ids = monitor.sample_ids(1)
            PLAY_SONG = ids[0] if ids else None
        except Exception:
            PLAY_SONG = None
    log(f"本轮播放目标: {PLAY_SONG}")
    r = refresh.refresh(play_song_id=PLAY_SONG, verbose=True)
    rec["refresh"] = r
    log(f"刷新 {'成功' if r['ok'] else '失败'}  "
        f"请求={r['weapi_hits']} 带伪IP={r['header_injected']} "
        f"player/url={r['player_url_calls']}(code={r.get('player_url_code')})")

    # 4. 刷新后状态
    time.sleep(2)
    post = monitor.check(SAMPLE)
    log(f"刷新后可播率 {post['ok']}/{post['total']} = {post['rate']:.0%}"
        + (f"  (err={post['error']})" if post["error"] else ""))
    rec["post"] = {"rate": post["rate"], "ok": post["ok"], "total": post["total"]}

    # 5. 结论
    good = post["rate"] >= THRESHOLD
    if good:
        rec["result"] = "ok"
        clear_alert()
        log(f"结论：正常（阈值 {THRESHOLD:.0%}）")
    else:
        rec["result"] = "fail"
        reason = post["error"] or f"可播率 {post['rate']:.0%} 低于阈值 {THRESHOLD:.0%}"
        log(f"结论：异常 —— {reason}")
        notify_fail(reason)

    rec["elapsed"] = round(time.time() - t0, 1)
    append_history(rec)
    log(f"本轮结束，用时 {rec['elapsed']}s")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
