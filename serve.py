#!/usr/bin/env python3
"""Serve the taste tool's pages on 127.0.0.1 and keep every answer in plain Markdown.

Run:  python3 serve.py [round]      then open http://127.0.0.1:8741/view (the tool), /judge (the current round), /plate, /pins, /capture, or / (the sites page)
sites.md, board-marks.md, and the plate's .md are the records, rewritten on every change.
"""
import json, re, sys, http.server, socketserver
import plate as plates
import view as views
import judge as judges
TEST = "test-2"  # the blind test served at /test (test 1 is in test-2026-10-07)
ROUND = sys.argv[1] if __name__ == "__main__" and len(sys.argv) > 1 else "plate-2026-10-07-round-3"  # the round served at /judge (`python3 serve.py <round>`; round 2 is judged; its marks stay in the data folder)
from datetime import datetime
from pathlib import Path

TOOL = Path(__file__).resolve().parent
from paths import DATA as HERE, EXTRA  # the data: references, marks, words, and the pages made from them (paths.py)
RECORD = HERE / "sites.md"
PORT = 8741
PLATE = "plate-2026-10-07"  # the plate served at /plate

# The only files this server will hand out.
FILES = {
    "/": (HERE / "judge-sites.html", "text/html; charset=utf-8"),
    "/pins": (HERE / "sort-pins.html", "text/html; charset=utf-8"),
    "/plate": (HERE / f"{PLATE}.html", "text/html; charset=utf-8"),
    "/view": (TOOL / "templates" / "view.html", "text/html; charset=utf-8"),
    "/judge": (HERE / f"judge-{ROUND}.html", "text/html; charset=utf-8"),
    "/test": (HERE / TEST / "compare.html", "text/html; charset=utf-8"),
    "/capture": (HERE / "studies-2026-10-07-capture.html", "text/html; charset=utf-8"),
    **EXTRA,
}

HEADER = """---
type: notes
purpose: My judgments of websites, liked and disliked, with why: the first references for the taste tool.
home: 00 Studio OS
private: yes
edits: both
created: 2026-10-07
updated: [{today}]
---

# Sites I judged

Kept by `judge-sites.html` (run `python3 serve.py`): every change on the page rewrites this file.
I can also edit it by hand while the page is closed.
"""

BLOCK = re.compile(r"^## (\d+) · (.+?) — (yes|some|no|unjudged)\n(\S+)\n- this part: (.*)\n- why: (.*)$", re.M)


def read_record():
    if not RECORD.exists():
        return {}
    out = {}
    for n, name, verdict, url, part, why in BLOCK.findall(RECORD.read_text()):
        out[n] = {"name": name, "url": url, "verdict": "" if verdict == "unjudged" else verdict,
                  "part": part.strip(), "why": why.strip()}
    return out


def write_record(entries):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [HEADER.format(today=today)]
    for n in sorted(entries, key=int):
        e = entries[n]
        one = lambda s: " ".join(str(s).split())  # one line per field
        lines.append(f"## {n} · {one(e['name'])} — {e.get('verdict') or 'unjudged'}\n{one(e['url'])}\n"
                     f"- this part: {one(e.get('part', ''))}\n- why: {one(e.get('why', ''))}\n")
    tmp = RECORD.with_suffix(".tmp")
    tmp.write_text("\n".join(lines))
    tmp.replace(RECORD)


MARKS = HERE / "board-marks.md"
MARKS_HEADER = """---
type: notes
purpose: Which pins on my board "data aesthetic" are there for the look, the idea, or both.
home: 00 Studio OS
private: yes
edits: both
created: 2026-10-07
updated: [{today}]
---

# The board, marked

Kept by `sort-pins.html` (run `python3 serve.py`, open /pins).
Numbers are the board's order on 2026-10-07, newest first; groups are Claude's, from `board-read-2026-10-07.md`.
"""
MARK_LINE = re.compile(r"^- (\d{3}) · (.*?) · (\S+)$", re.M)


def read_marks():
    if not MARKS.exists():
        return []
    out, kind = [], None
    for line in MARKS.read_text().splitlines():
        if line.startswith("## for "):
            kind = {"the look": "look", "the idea": "idea", "both": "both"}.get(line[7:].split(" (")[0].strip())
        m = MARK_LINE.match(line)
        if m and kind:
            out.append({"n": m[1], "k": kind, "group": m[2], "url": m[3]})
    return out


def write_marks(items):
    today = datetime.now().strftime("%Y-%m-%d")
    parts = [MARKS_HEADER.format(today=today)]
    for kind, title in (("look", "the look"), ("idea", "the idea"), ("both", "both")):
        rows = sorted((i for i in items if i["k"] == kind), key=lambda i: i["n"])
        parts.append(f"## for {title} ({len(rows)})\n" + "".join(f"- {i['n']} · {i['group']} · {i['url']}\n" for i in rows))
    tmp = MARKS.with_suffix(".tmp")
    tmp.write_text("\n".join(parts))
    tmp.replace(MARKS)


class Handler(http.server.BaseHTTPRequestHandler):
    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/answers":
            return self.send(200, json.dumps(read_record()).encode(), "application/json")
        if self.path == "/pin-marks":
            return self.send(200, json.dumps(read_marks()).encode(), "application/json")
        if self.path == "/plate-marks":
            f = HERE / f"{PLATE}.marks.json"
            return self.send(200, f.read_bytes() if f.exists() else b"{}", "application/json")
        if self.path.startswith("/judge-marks"):
            f = HERE / f"{ROUND}-marks.json"
            return self.send(200, f.read_bytes() if f.exists() else b"{}", "application/json")
        if self.path == "/view-data":
            return self.send(200, json.dumps(views.data()).encode(), "application/json")
        if self.path.startswith("/file/"):
            from urllib.parse import unquote
            f = (HERE / unquote(self.path[6:])).resolve()
            kinds = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
            if HERE in f.parents and f.suffix in kinds and f.exists():
                return self.send(200, f.read_bytes(), kinds[f.suffix])
            return self.send(404, b"not here", "text/plain")
        m = re.fullmatch(r"/tests/(test-[a-z0-9-]+)/(x-(?:default|profile|pulled)\.html)", self.path)
        if m:
            f = HERE / m[1] / m[2]
            return self.send(200, f.read_bytes(), "text/html; charset=utf-8") if f.exists() else self.send(404, b"not here", "text/plain")
        if self.path in ("/test/i", "/test/ii"):
            key = json.loads((HERE / TEST / "key.json").read_text())
            f = HERE / TEST / key[self.path[6:]]
            return self.send(200, f.read_bytes(), "text/html; charset=utf-8") if f.exists() else self.send(404, b"not made yet", "text/plain")
        if self.path == "/test-key":
            return self.send(200, (HERE / TEST / "key.json").read_bytes(), "application/json")
        if self.path == "/test-verdict":
            f = HERE / TEST / "verdict.json"
            return self.send(200, f.read_bytes() if f.exists() else b"{}", "application/json")
        m = re.fullmatch(r"/plate-img/([0-9]{2}-[a-z0-9-]+)\.jpg", self.path)
        if m:
            f = HERE / PLATE / f"{m[1]}.jpg"
            return self.send(200, f.read_bytes(), "image/jpeg") if f.exists() else self.send(404, b"not here", "text/plain")
        f = FILES.get(self.path)
        if not f or not f[0].exists():
            return self.send(404, b"not here", "text/plain")
        self.send(200, f[0].read_bytes(), f[1])

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/answers":
            write_record(json.loads(body))
        elif self.path == "/pin-marks":
            write_marks(json.loads(body))
        elif self.path == "/judge-marks":
            marks = json.loads(body)
            tmp = HERE / f"{ROUND}-marks.json.tmp"
            tmp.write_text(json.dumps({"pages": marks.get("pages", {})}))
            tmp.replace(HERE / f"{ROUND}-marks.json")
            judges.marks_to_markdown(ROUND, marks)
        elif self.path == "/pulled":
            ids = json.loads(body)
            mats = {m["id"]: m for m in json.loads((HERE / "library" / "materials.json").read_text())}
            lines = [f"- `{i}` {mats[i]['kind']}: {mats[i]['name']} (from {', '.join(s['page'] for s in mats[i]['sources'][:3])})" for i in ids if i in mats]
            (HERE / "library" / "pulled.md").write_text(f"""---
type: notes
purpose: The materials I've pulled from the library for the next thing to make. Kept by the library page; an agent making something reads this, then records what it used in uses.md.
home: 00 Studio OS
private: yes
edits: both
created: 2026-10-07
updated: [{datetime.now().strftime("%Y-%m-%d")}]
---

# Pulled

""" + "\n".join(lines) + "\n")
        elif self.path == "/test-verdict":
            v = json.loads(body)
            (HERE / TEST / "verdict.json").write_text(json.dumps(v))
            key = json.loads((HERE / TEST / "key.json").read_text())
            who = {"x-profile.html": "started from my profile", "x-pulled.html": "pulled from my library", "x-default.html": "Claude's own habits"}
            pick = {"i": f"i ({who[key['i']]})", "ii": f"ii ({who[key['ii']]})"}.get(v.get("verdict"), v.get("verdict") or "not chosen yet")
            (HERE / TEST / "verdict.md").write_text(f"""---
type: notes
purpose: My verdict on {TEST}: the same page made from Claude's habits and from my taste.
home: 00 Studio OS
private: yes
edits: both
created: 2026-10-07
updated: [{datetime.now().strftime("%Y-%m-%d")}]
---

# Two pages, same words: my verdict

- more me: {pick}
- why: {" ".join((v.get("why") or "").split())}
- which was which: {"not revealed yet" if not v.get("revealed") else "revealed before I chose" if v.get("revealedBeforeChoosing") else "revealed after I chose"}
""")
        elif self.path == "/plate-marks":
            marks = json.loads(body)
            tmp = HERE / f"{PLATE}.marks.json.tmp"
            tmp.write_text(json.dumps({"cards": marks.get("cards", {})}))
            tmp.replace(HERE / f"{PLATE}.marks.json")
            plates.marks_to_markdown(PLATE, marks)
        else:
            return self.send(404, b"not here", "text/plain")
        self.send(200, b'{"kept":true}', "application/json")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as s:
        print(f"http://127.0.0.1:{PORT}")
        s.serve_forever()
