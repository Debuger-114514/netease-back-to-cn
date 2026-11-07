# -*- coding: utf-8 -*-
"""
刷新器：用无头 Edge 1:1 复现"开网页 → 带伪 IP 访问 → 播放"这套动作
  1. 从客户端解出的 MUSIC_U 注入，免登录
  2. 所有请求带 X-Real-IP，等价于你那支 NetEaseMusicWorld+
  3. 打开页面 + 尝试播放，让服务端把账号按国内处理
"""
import os
import sys
import json
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import cred

REAL_IP = os.environ.get("NE_REAL_IP", "211.161.244.70")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HOME = "https://music.163.com/"
COOKIE_KEYS = ("MUSIC_U", "MUSIC_A_T", "MUSIC_R_T", "__csrf", "NMTID",
               "deviceId", "os", "appver", "osver", "channel")

# 页面内直接触发播放（locator 在无头模式下不稳定，JS 点击更可靠，且能兜底模糊匹配）
PLAY_JS = r"""() => {
  const sels = ['.ply.j-flag', 'a.ply', '.u-btni-play', '.btn-ply', '[data-action="play"]'];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el) { try { el.click(); } catch (e) {} return s; }
  }
  const cand = Array.from(document.querySelectorAll('a,button,span'));
  const hit = cand.find(e => /\bply\b|\bplay\b/i.test(e.className || ''));
  if (hit) { try { hit.click(); } catch (e) {} return 'fuzzy:' + hit.className; }
  return null;
}"""


def _pw_cookies(c: dict):
    """全量注入：含 JSESSIONID-WYYY 等会话 cookie，否则 weapi 会报“参数错误”"""
    return [x for x in c.get("__full__", []) if x.get("value")]


def refresh(play_song_id=None, dwell=9, verbose=True) -> dict:
    """
    跑一遍刷新。返回统计信息，不抛异常（失败也在 result 里体现）。
    """
    result = {
        "ok": False,
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "weapi_hits": 0,
        "header_injected": 0,
        "player_url_calls": 0,
        "player_url_ok": 0,
        "player_url_code": None,
        "cdns_ok": False,
        "error": None,
    }

    def say(*a):
        if verbose:
            print(*a)

    try:
        cookies = cred.get_cred()
    except Exception as e:
        result["error"] = f"凭据不可用: {e}"
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="msedge", headless=True,
                args=["--mute-audio", "--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 900})
            ctx.set_extra_http_headers({"X-Real-IP": REAL_IP})
            ctx.add_cookies(_pw_cookies(cookies))
            page = ctx.new_page()

            def on_request(req):
                u = req.url
                if "music.163.com" not in u:
                    return
                if "/weapi/" in u or "/eapi/" in u or "/api/" in u:
                    result["weapi_hits"] += 1
                    if req.headers.get("x-real-ip") == REAL_IP:
                        result["header_injected"] += 1

            pu_bodies = []

            def on_response(resp):
                u = resp.url
                if "enhance/player/url" in u:
                    result["player_url_calls"] += 1
                    try:
                        pu_bodies.append(resp.json())
                    except Exception:
                        pass
                elif "weapi/cdns" in u:
                    result["cdns_ok"] = True

            page.on("request", on_request)
            page.on("response", on_response)

            say(f"[refresh] 打开首页（X-Real-IP={REAL_IP}）")
            page.goto(HOME, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(dwell * 1000)

            # 走一遍"我的音乐"，更接近真实使用
            for path in ("/my/", "/discover/toplist"):
                try:
                    page.goto("https://music.163.com" + path, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3500)
                except PWTimeout:
                    pass

            # 播放（可选；网页版对部分歌会引导去客户端，失败不影响刷新）
            if play_song_id:
                say(f"[refresh] 打开并尝试播放歌曲 {play_song_id}")
                try:
                    page.goto(f"https://music.163.com/song?id={play_song_id}",
                              timeout=35000, wait_until="domcontentloaded")
                    page.wait_for_timeout(6000)
                    clicked = None
                    for fr in [page] + list(page.frames):
                        try:
                            hit = fr.evaluate(PLAY_JS)
                        except Exception:
                            continue
                        if hit:
                            clicked = hit
                            break
                    say(f"[refresh] 播放按钮: {clicked or '未找到'}")
                    page.wait_for_timeout(7000)
                except PWTimeout:
                    say("[refresh] 歌曲页超时，跳过")

            for d in pu_bodies:
                try:
                    x = (d.get("data") or [{}])[0]
                    if x.get("url"):
                        result["player_url_ok"] += 1
                    if result.get("player_url_code") is None:
                        result["player_url_code"] = x.get("code")
                except Exception:
                    pass

            browser.close()

        result["ok"] = result["weapi_hits"] > 0 and result["header_injected"] > 0 and result["cdns_ok"]
        if not result["ok"] and not result["error"]:
            result["error"] = (f"请求异常 weapi={result['weapi_hits']} "
                               f"带IP={result['header_injected']} cdns={result['cdns_ok']}")
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)[:220]}"

    say(f"[refresh] 完成 weapi={result['weapi_hits']} 带IP={result['header_injected']} "
        f"player/url 调用={result['player_url_calls']} 成功={result['player_url_ok']} "
        f"cdns={result['cdns_ok']} => {'OK' if result['ok'] else 'FAIL ' + str(result['error'])}")
    return result


if __name__ == "__main__":
    sid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    r = refresh(play_song_id=sid)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r["ok"] else 1)
