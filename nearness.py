#!/usr/bin/env python3
"""Nearness, after PseudoClient (Lin & Martelaro, DIS 2021): a new thing is compared with each
thing I liked, one by one, and its nearness is the median of those comparisons, never a match
against an average. Images become vectors with Apple's Vision feature prints (featureprint.swift),
already on every Mac; nothing is trained and nothing is downloaded.

  python3 nearness.py        writes the data folder's nearness/nearness.md and nearness.json

It also checks itself: does it put the things I said yes to nearer than the things I said no to?
The answer is a number between 0 and 1 (0.5 is chance), and says how many judgments it rests on.
"""
import json, re, subprocess
from pathlib import Path
from statistics import median

import library as lib

TOOL = Path(__file__).resolve().parent
DATA = lib.DATA
OUT = DATA / "nearness"
BIN = OUT / "featureprint"


def ensure_binary():
    src = TOOL / "featureprint.swift"
    if not BIN.exists() or BIN.stat().st_mtime < src.stat().st_mtime:
        OUT.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", "-O", str(src), "-o", str(BIN)], check=True)


def prints(paths):
    cache_f = OUT / "prints.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    todo = [str(p) for p in paths if str(p) not in cache]
    for i in range(0, len(todo), 60):
        tmp = OUT / "prints.tmp.json"
        subprocess.run([str(BIN), str(tmp)] + todo[i:i + 60], check=True, capture_output=True)
        cache.update(json.loads(tmp.read_text()))
        tmp.unlink()
    cache_f.write_text(json.dumps(cache))
    return cache


def dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def pin_marks():
    marks = {}
    f = DATA / "board-marks.md"
    kind = None
    for line in f.read_text().splitlines():
        if line.startswith("## for "):
            kind = {"the look": "look", "the idea": "idea", "both": "both"}.get(line[7:].split(" (")[0].strip())
        m = re.match(r"^- (\d{3}) · ", line)
        if m and kind:
            marks[m[1]] = kind
    return marks


def page_marks():
    """My yes and no on whole pages: from the round judged on its page, and from my walk (mine = yes, not mine = no)."""
    out = {}
    for stem, v in lib.verdicts().items():
        if v == "mine":
            out[stem] = "yes"
        elif v == "not mine":
            out[stem] = "no"
    for f in DATA.glob("plate-*-marks.json"):
        for stem, m in json.loads(f.read_text()).get("pages", {}).items():
            if m.get("page") in ("yes", "no"):
                out[stem] = m["page"]
    return out


def auc(pos, neg):
    """How often a yes sits nearer than a no (smaller median distance). 0.5 is chance."""
    if not pos or not neg:
        return None
    wins = sum(1.0 if p < n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def run():
    ensure_binary()
    pins = {p.name[:3]: p for p in sorted((DATA / "pins").glob("*.jpg"))}
    pm = pin_marks()
    caps = lib.captures()
    pages = page_marks()
    fp = prints(list(pins.values()) + [c["jpg"] for c in caps])
    vec = lambda p: fp.get(str(p))

    liked_pins = [n for n, k in pm.items() if k in ("look", "both") and vec(pins.get(n))]
    liked_pages = [c["stem"] for c in caps if pages.get(c["stem"]) == "yes"]
    capv = {c["stem"]: vec(c["jpg"]) for c in caps}

    def near(v, support, exclude=None):
        ds = [dist(v, s) for k, s in support if k != exclude]
        return median(ds) if ds else None

    pin_support = [(n, vec(pins[n])) for n in liked_pins]
    page_support = [(s, capv[s]) for s in liked_pages if capv.get(s)]

    # every page, near my liked pins and near my liked pages (leave-one-out for the page itself)
    rows = []
    for c in caps:
        v = capv.get(c["stem"])
        if not v:
            continue
        rows.append({"stem": c["stem"], "name": c["name"], "url": c["url"], "mark": pages.get(c["stem"], ""),
                     "near_pins": near(v, pin_support), "near_pages": near(v, page_support, exclude=c["stem"])})

    # the self-check: do my yes pages sit nearer than my no pages?
    yes = [r for r in rows if r["mark"] == "yes"]
    no = [r for r in rows if r["mark"] == "no"]
    checks = {
        "pages_by_pins": auc([r["near_pins"] for r in yes], [r["near_pins"] for r in no]),
        "pages_by_pages": auc([r["near_pages"] for r in yes if r["near_pages"] is not None], [r["near_pages"] for r in no if r["near_pages"] is not None]),
        "yes": len(yes), "no": len(no),
    }
    # and on the pins: does a look pin sit nearer my other look pins than an idea pin does?
    look_scores = [near(vec(pins[n]), pin_support, exclude=n) for n in liked_pins]
    idea_scores = [near(vec(pins[n]), pin_support) for n, k in pm.items() if k == "idea" and vec(pins.get(n))]
    checks["pins_look_vs_idea"] = auc(look_scores, idea_scores)
    checks["look_pins"], checks["idea_pins"] = len(look_scores), len(idea_scores)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "nearness.json").write_text(json.dumps({"rows": rows, "checks": checks}, indent=1))
    write_md(rows, checks, len(pin_support), len(page_support))
    return rows, checks


def fmt(x):
    return "—" if x is None else f"{x:.2f}"


def write_md(rows, checks, n_pins, n_pages):
    def verdict(a):
        if a is None:
            return "can't tell yet: it needs at least one yes and one no"
        return "no better than chance" if a < 0.6 else "some signal" if a < 0.75 else "a clear signal"
    lines = [f"""---
type: notes
purpose: Nearness after PseudoClient: each page's median distance to the things I liked, and whether that agrees with my own yes and no. Computed by tools/physiognomy/nearness.py; don't edit by hand.
home: 00 Studio OS
private: yes
edits: agents
created: 2026-10-07
updated: [2026-10-07]
---

# Nearness

Each image becomes a vector (Apple's Vision feature print). A page's nearness is the **median** distance from it to each thing I liked, one by one: smaller is nearer. Liked means the {n_pins} pins I marked for the look or both, and, separately, the {n_pages} whole pages I said yes to.

## does it work?

A number from 0 to 1 for how often something I said yes to sits nearer than something I said no to. 0.5 is chance; 1 is always.

- Pages, measured against my liked pins: **{fmt(checks['pages_by_pins'])}** ({verdict(checks['pages_by_pins'])}), from {checks['yes']} yes and {checks['no']} no.
- Pages, measured against my other liked pages: **{fmt(checks['pages_by_pages'])}** ({verdict(checks['pages_by_pages'])}).
- Pins: a pin I liked for the look, against my other look pins, versus a pin I liked only for the idea: **{fmt(checks['pins_look_vs_idea'])}** ({verdict(checks['pins_look_vs_idea'])}), from {checks['look_pins']} and {checks['idea_pins']} pins.

These rest on few judgments; treat them as a first reading, not a result.

## pages, nearest my liked pages first

| page | my mark | near my liked pages | near my liked pins |
|---|---|---|---|
"""]
    for r in sorted(rows, key=lambda r: (r["near_pages"] is None, r["near_pages"] or 0)):
        lines.append(f"| {r['name']} | {r['mark']} | {fmt(r['near_pages'])} | {fmt(r['near_pins'])} |")
    (OUT / "nearness.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    rows, checks = run()
    print(json.dumps(checks, indent=1))
