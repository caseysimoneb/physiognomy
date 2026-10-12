#!/usr/bin/env python3
"""Render local pages to PNG with the installed Chrome, headless, to check them before showing anyone.

  python3 snap.py out-dir name=url[@WxH][@dark] ...
"""
import base64, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from capture import Tab, CHROME

PORT = 9231


def main(out, specs):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    ch = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={tempfile.mkdtemp()}",
                           "--hide-scrollbars", "--no-first-run", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1); break
        except Exception:
            time.sleep(0.2)
    try:
        for spec in specs:
            name, rest = spec.split("=", 1)
            parts = rest.split("@")
            url, w, h, scheme = parts[0], 1440, 900, "light"
            for p in parts[1:]:
                if "x" in p: w, h = map(int, p.split("x"))
                elif p in ("dark", "light"): scheme = p
            t = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")))
            tab = Tab(t["webSocketDebuggerUrl"]); tab.send("Page.enable")
            tab.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=w < 500)
            tab.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": scheme}])
            tab.send("Page.navigate", url=url); tab.wait_for("Page.loadEventFired", 20); time.sleep(2.5)
            s = tab.send("Page.captureScreenshot", format="png")
            (out / f"{name}.png").write_bytes(base64.b64decode(s["data"]))
            tab.sock.close(); urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/close/{t['id']}")
            print(name)
    finally:
        ch.terminate()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
