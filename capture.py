#!/usr/bin/env python3
"""Capture websites for a plate: a picture of the first screen and, at the same moment,
what's on it (typefaces, sizes, colours, spacing, and every visible text block's box).

Uses the Google Chrome already installed, headless, with a throwaway profile, so
nothing is downloaded and the everyday Chrome profile is never touched.
Sites that block headless browsers are reported, not worked around.

Run:  python3 capture.py plate-2026-10-07 sites.txt
sites.txt: one site per line, "name | url".
Writes <plate>/NN-slug.jpg and <plate>/NN-slug.json.
"""
import base64, json, os, re, socket, struct, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9227
W, H = 1440, 900

# Read in the page: the first screen's text blocks and a summary of its values.
MEASURE = r"""
(() => {
  const W = innerWidth, H = innerHeight;
  const first = f => (f || '').split(',')[0].replace(/["']/g, '').trim();
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c; } return getComputedStyle(document.documentElement).backgroundColor || 'rgb(255, 255, 255)'; };
  const blocks = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const t = walker.currentNode; const txt = t.textContent.replace(/\s+/g, ' ').trim();
    if (txt.length < 2) continue;
    const el = t.parentElement; if (!el || seen.has(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > H || r.right < 0 || r.left > W) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || +s.opacity === 0) continue;
    seen.add(el);
    blocks.push({ x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height),
      tag: el.tagName.toLowerCase(), font: first(s.fontFamily), size: parseFloat(s.fontSize), weight: s.fontWeight,
      style: s.fontStyle, line: s.lineHeight, tracking: s.letterSpacing, case: s.textTransform,
      color: s.color, bg: bgOf(el), text: txt.slice(0, 60), chars: txt.length });
    if (blocks.length > 400) break;
  }
  // spacing: paddings, margins, gaps of visible boxes on the first screen
  const space = {};
  for (const el of document.body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect(); if (r.width < 8 || r.height < 8 || r.top > H || r.bottom < 0) continue;
    const s = getComputedStyle(el);
    for (const v of [s.paddingTop, s.paddingLeft, s.marginTop, s.marginBottom, s.rowGap, s.columnGap]) {
      const n = Math.round(parseFloat(v)); if (n > 0 && n < 400) space[n] = (space[n] || 0) + 1;
    }
  }
  const paras = blocks.filter(b => b.chars > 120);
  return { url: location.href, title: document.title, viewport: [W, H], dpr: devicePixelRatio,
    page_bg: getComputedStyle(document.body).backgroundColor, blocks, space,
    measure_px: paras.map(b => b.w), fonts_loaded: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/["']/g, '')) };
})()
"""

# The privacy-preserving answer to a consent banner, if there is an obvious one.
DECLINE = r"""
(() => {
  const words = /^(reject all|reject|decline|decline all|only necessary|necessary only|use necessary cookies only|refuse|deny|no thanks)$/i;
  for (const b of document.querySelectorAll('button, [role=button], a')) {
    const t = (b.innerText || '').trim();
    if (words.test(t)) { b.click(); return t; }
  }
  return null;
})()
"""


class Tab:
    """A minimal Chrome DevTools Protocol client over a websocket (standard library only)."""

    def __init__(self, ws_url):
        m = re.match(r"ws://([^/:]+):(\d+)(/.*)", ws_url)
        self.sock = socket.create_connection((m[1], int(m[2])), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {m[3]} HTTP/1.1\r\nHost: {m[1]}:{m[2]}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        self.buf = resp.split(b"\r\n\r\n", 1)[1]
        self.n = 0
        self.events = []

    def _recv_exact(self, k):
        while len(self.buf) < k:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise ConnectionError("closed")
            self.buf += chunk
        out, self.buf = self.buf[:k], self.buf[k:]
        return out

    def _read(self):
        msg = b""
        while True:
            b1, b2 = self._recv_exact(2)
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._recv_exact(8))[0]
            msg += self._recv_exact(ln)
            if b1 & 0x80:
                return json.loads(msg)

    def send(self, method, **params):
        self.n += 1
        data = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        mask = os.urandom(4)
        head = bytes([0x81])
        ln = len(data)
        head += bytes([0x80 | ln]) if ln < 126 else (bytes([0x80 | 126]) + struct.pack(">H", ln) if ln < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", ln))
        self.sock.sendall(head + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))
        while True:
            m = self._read()
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})
            self.events.append(m)

    def wait_for(self, method, timeout):
        end = time.time() + timeout
        self.sock.settimeout(1)
        try:
            while time.time() < end:
                if any(e.get("method") == method for e in self.events):
                    return True
                try:
                    self.events.append(self._read())
                except socket.timeout:
                    pass
            return False
        finally:
            self.sock.settimeout(60)

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def main(plate, listfile):
    out = Path(plate)
    out.mkdir(exist_ok=True)
    sites = [l.split("|", 1) for l in Path(listfile).read_text().splitlines() if "|" in l and not l.lstrip().startswith("#")]
    profile = tempfile.mkdtemp(prefix="taste-chrome-")
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                               "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--mute-audio",
                               f"--window-size={W},{H}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        report = []
        for i, (name, url) in enumerate(sites, 1):
            name, url = name.strip(), url.strip()
            stem = f"{i:02d}-{slug(name)}"
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")
            target = json.load(urllib.request.urlopen(req))
            tab = Tab(target["webSocketDebuggerUrl"])
            note = ""
            try:
                tab.send("Page.enable")
                tab.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
                tab.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
                nav = tab.send("Page.navigate", url=url)
                if nav.get("errorText"):
                    raise RuntimeError(nav["errorText"])
                tab.wait_for("Page.loadEventFired", 25)
                time.sleep(2.5)
                declined = tab.js(DECLINE)
                if declined:
                    note += f"declined a consent banner ({declined}). "
                    time.sleep(1.2)
                tab.js("window.scrollTo(0, document.body.scrollHeight * 0.5)")
                time.sleep(1.0)
                tab.js("window.scrollTo(0, 0)")
                tab.js("document.fonts.ready.then(() => true)")
                time.sleep(1.2)
                facts = tab.js(MEASURE) or {}
                shot = tab.send("Page.captureScreenshot", format="jpeg", quality=82,
                                clip={"x": 0, "y": 0, "width": W, "height": H, "scale": 1})
                (out / f"{stem}.jpg").write_bytes(base64.b64decode(shot["data"]))
                facts.update({"name": name, "asked_url": url, "captured": time.strftime("%Y-%m-%d %H:%M"), "note": note.strip()})
                (out / f"{stem}.json").write_text(json.dumps(facts, indent=1))
                report.append(f"{stem}: ok, {len(facts.get('blocks', []))} text blocks. {note}")
            except Exception as e:
                report.append(f"{stem}: FAILED {e}")
            finally:
                try:
                    tab.sock.close()
                    urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/close/{target['id']}", timeout=3)
                except Exception:
                    pass
            print(report[-1], flush=True)
    finally:
        chrome.terminate()
        chrome.wait(timeout=10)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
