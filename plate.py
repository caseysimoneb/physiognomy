#!/usr/bin/env python3
"""A plate: captured sites laid out on one sheet to mark, and what the marks measure.

  python3 plate.py build plate-2026-10-07     makes <data>/plate-2026-10-07.html from the captures there
  (serve.py calls marks_to_markdown when the page saves)

Each capture is NN-slug.jpg + NN-slug.json from capture.py.
The marks live in <plate>.marks.json (stroke geometry) and <plate>.md (the record, readable).
"""
import json, random, re, sys
from collections import Counter
from datetime import datetime
from pathlib import Path

TOOL = Path(__file__).resolve().parent
from paths import DATA as HERE  # the data (paths.py)
W, H = 1440, 900


def rgb_hex(c):
    m = re.findall(r"[\d.]+", c or "")
    if len(m) < 3:
        return None
    if len(m) == 4 and float(m[3]) == 0:
        return None
    return "#%02X%02X%02X" % tuple(round(float(v)) for v in m[:3])


def summarize(blocks, space=None):
    """The values of a set of text blocks, weighted by how much text each holds."""
    if not blocks:
        return {}
    fonts, sizes, ink, ground = Counter(), Counter(), Counter(), Counter()
    for b in blocks:
        n = max(b.get("chars", 1), 1)
        fonts[b["font"]] += n
        if b["size"] >= 1:
            sizes[round(b["size"])] += n
        if rgb_hex(b["color"]):
            ink[rgb_hex(b["color"])] += n
        if rgb_hex(b["bg"]):
            ground[rgb_hex(b["bg"])] += n
    body = sizes.most_common(1)[0][0]
    steps = sorted(sizes)
    out = {
        "fonts": [f for f, _ in fonts.most_common(3)],
        "sizes": steps[:8],
        "body": body,
        "largest_over_body": round(max(steps) / body, 2) if body else None,
        "ink": [c for c, _ in ink.most_common(3)],
        "ground": [c for c, _ in ground.most_common(2)],
        "cases": sorted({b["case"] for b in blocks if b.get("case") not in (None, "none")}),
    }
    if space:
        out["spacing"] = [int(k) for k, _ in sorted(space.items(), key=lambda kv: -kv[1])[:5]]
    return out


def captures(plate):
    d = HERE / plate
    return sorted(d.glob("*.json"))


def build(plate):
    cards = []
    for j in captures(plate):
        f = json.loads(j.read_text())
        s = summarize(f.get("blocks", []), f.get("space"))
        cards.append({"stem": j.stem, "name": f["name"], "url": f["asked_url"],
                      "host": re.sub(r"^https?://(www\.)?", "", f["asked_url"]).rstrip("/"),
                      "note": f.get("note", ""), "facts": s})
    random.Random(plate).shuffle(cards)  # mixed, not ranked; the same order every time
    for i, c in enumerate(cards, 1):
        c["no"] = f"{i:02d}"
    tpl = (TOOL / "templates" / "plate.template.html").read_text()
    html = tpl.replace("/*CARDS*/[]", json.dumps(cards)).replace("{{PLATE}}", plate)
    (HERE / f"{plate}.html").write_text(html)
    print(f"{plate}.html: {len(cards)} cards")


def marks_to_markdown(plate, marks):
    """Write the readable record: per card, what was kept, struck, and why, with what the kept parts measure."""
    facts = {j.stem: json.loads(j.read_text()) for j in captures(plate)}
    order = {c["stem"]: c for c in marks.get("cards_meta", [])}
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"""---
type: notes
purpose: My marks on {plate}: which sites, and which parts of them, I kept or struck, and why.
home: 00 Studio OS
private: yes
edits: both
created: 2026-10-07
updated: [{today}]
---

# {plate}, marked

Kept by `{plate}.html` (run `python3 serve.py`, open /plate).
A loop in blue keeps a part; a strike says not this. What a kept part measures comes from the page as it was captured, not from the picture.
"""]
    kept_parts = []
    for stem, m in sorted(marks.get("cards", {}).items(), key=lambda kv: order.get(kv[0], {}).get("no", kv[0])):
        strokes = m.get("strokes", [])
        why = " ".join((m.get("why") or "").split())
        if not strokes and not why:
            continue
        f = facts.get(stem, {})
        meta = order.get(stem, {})
        keeps = [s for s in strokes if s["ink"] == "keep"]
        nots = [s for s in strokes if s["ink"] == "not"]
        verdict = "kept" if keeps and not nots else "struck" if nots and not keeps else "both kept and struck" if keeps else "a note only"
        lines.append(f"## {meta.get('no', '')} · {f.get('name', stem)} — {verdict}")
        lines.append(f.get("asked_url", ""))
        if why:
            lines.append(f"- why: {why}")
        for ink, group in (("kept", keeps), ("struck", nots)):
            for s in group:
                xs = [p[0] for p in s["pts"]]
                ys = [p[1] for p in s["pts"]]
                x0, x1, y0, y1 = min(xs) * W, max(xs) * W, min(ys) * H, max(ys) * H
                inside = [b for b in f.get("blocks", []) if x0 <= b["x"] + b["w"] / 2 <= x1 and y0 <= b["y"] + b["h"] / 2 <= y1]
                where = f"x {round(x0)}–{round(x1)}, y {round(y0)}–{round(y1)}"
                if inside:
                    v = summarize(inside)
                    sample = "; ".join(f"“{b['text'][:30]}”" for b in inside[:2])
                    lines.append(f"- {ink} ({where}): {', '.join(v['fonts'])} · sizes {', '.join(map(str, v['sizes']))} · ink {', '.join(v['ink'])} on {', '.join(v['ground'])} · {sample}")
                    if ink == "kept":
                        kept_parts.append(v)
                else:
                    lines.append(f"- {ink} ({where}): no text inside; a picture or empty space")
        lines.append("")
    tmp = HERE / f"{plate}.md.tmp"
    tmp.write_text("\n".join(lines))
    tmp.replace(HERE / f"{plate}.md")


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(sys.argv[2])
