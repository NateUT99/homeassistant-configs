"""Screenshot a home-main view or pop-up in WebKit at iPhone size, for dashboard tuning.

WebKit is Safari's engine, the same one the iPhone Companion app renders with. The browser
logs in as the non-admin "Dashboard Preview" HA user, so it can see the dashboard but not
change configuration. It only navigates and screenshots; it never taps controls.

Setup (one time, outside the repo):
    python3 -m venv ~/.local/share/ha-preview/venv
    ~/.local/share/ha-preview/venv/bin/pip install playwright pillow
    PLAYWRIGHT_BROWSERS_PATH=~/.local/share/ha-preview/browsers \
        ~/.local/share/ha-preview/venv/bin/playwright install webkit
    Token: a long-lived token created by the Dashboard Preview user, saved with
        pbpaste > ~/.config/ha-preview/token && chmod 600 ~/.config/ha-preview/token
    Revoke by deleting the token (or the user) in HA.

Usage:
    PLAYWRIGHT_BROWSERS_PATH=~/.local/share/ha-preview/browsers \
        ~/.local/share/ha-preview/venv/bin/python scripts/dashboard_preview.py '#climate' out.png ["js expr"]
    '-' as the hash screenshots the view without opening a pop-up.

Environment:
    VIEW=climate      view path to load (default home)
    SCROLL=700        scroll the open pop-up by N px before the screenshot
    THEME=file.json   preview a trial theme ({"modes": {...}}) in place of the views' theme;
                      HA's websocket replies are rewritten in this browser only, nothing is
                      written to HA

The optional third argument is a JavaScript expression evaluated in the page; its result is
printed (used to inspect Bubble Card's shadow DOM). The token is never printed.

Must run outside the Claude Code sandbox (the browser needs network access).
"""
import json
import os
import pathlib
import socket
import sys
import threading
import time

from playwright.sync_api import sync_playwright

HA = ("homeassistant.lan", 80)
PORT = 18123
BASE = f"http://127.0.0.1:{PORT}"


# macOS Local Network privacy blocks the Playwright WebKit app bundle from reaching the LAN
# (it reports "The Internet connection appears to be offline"), while this process, started
# from the terminal, is allowed. Relay loopback -> HA over plain TCP; loopback isn't gated.
def _pipe(a, b):
    try:
        while d := a.recv(65536):
            b.sendall(d)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _forward():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(64)
    while True:
        c, _ = srv.accept()
        u = socket.create_connection(HA)
        threading.Thread(target=_pipe, args=(c, u), daemon=True).start()
        threading.Thread(target=_pipe, args=(u, c), daemon=True).start()


def _trial_theme_patcher(trial):
    def patch(msg):
        if not isinstance(msg, str) or ('"themes"' not in msg and '"views"' not in msg):
            return msg
        data = json.loads(msg)
        for m in data if isinstance(data, list) else [data]:
            if not isinstance(m, dict):
                continue
            r = m.get("result")
            if not isinstance(r, dict):
                ev = m.get("event")
                r = ev if isinstance(ev, dict) and "themes" in ev else None
            if not r:
                continue
            if isinstance(r.get("themes"), dict):
                r["themes"]["Trial"] = trial
            for v in r.get("views", []) if isinstance(r.get("views"), list) else []:
                if v.get("theme"):
                    v["theme"] = "Trial"
        return json.dumps(data)

    return patch


def main():
    hash_, out = sys.argv[1], sys.argv[2]
    js = sys.argv[3] if len(sys.argv) > 3 else None
    threading.Thread(target=_forward, daemon=True).start()
    token = pathlib.Path("~/.config/ha-preview/token").expanduser().read_text().strip()
    tokens = json.dumps({
        "access_token": token, "token_type": "Bearer", "expires_in": 10**9,
        "refresh_token": "", "hassUrl": BASE, "clientId": BASE + "/",
        "expires": int(time.time() * 1000) + 10**12,
    })

    with sync_playwright() as p:
        browser = p.webkit.launch()
        ctx = browser.new_context(**p.devices["iPhone 15 Pro"], color_scheme="dark")
        ctx.add_init_script(f"localStorage.setItem('hassTokens', {json.dumps(tokens)});")
        page = ctx.new_page()

        if os.environ.get("THEME"):
            patch = _trial_theme_patcher(json.loads(pathlib.Path(os.environ["THEME"]).read_text()))

            def on_ws(route):
                server = route.connect_to_server()
                route.on_message(lambda m: server.send(m))
                server.on_message(lambda m: route.send(patch(m)))

            page.route_web_socket(lambda url: url.endswith("/api/websocket"), on_ws)

        page.goto(f"{BASE}/home-main/{os.environ.get('VIEW', 'home')}", wait_until="networkidle")
        page.wait_for_timeout(4000)
        if hash_ and hash_ != "-":
            page.evaluate(f"window.location.hash = {json.dumps(hash_)}")
            page.wait_for_timeout(6000)
        if scroll := int(os.environ.get("SCROLL", "0")):
            # Bubble pop-ups scroll inside a shadow-DOM container, not the page.
            page.evaluate(
                """(y) => { const all = []; const walk = r => r.querySelectorAll('*').forEach(e => {
                     all.push(e); if (e.shadowRoot) walk(e.shadowRoot); }); walk(document);
                   for (const e of all) { if (e.scrollHeight > e.clientHeight + 50
                     && /auto|scroll/.test(getComputedStyle(e).overflowY) && e.offsetParent !== null
                     && String(e.className).includes('pop-up')) e.scrollTop = y; } }""",
                scroll,
            )
            page.wait_for_timeout(1500)
        page.screenshot(path=out)
        if js:
            print(page.evaluate(js))
        browser.close()


if __name__ == "__main__":
    main()
