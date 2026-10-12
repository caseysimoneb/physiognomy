#!/usr/bin/env python3
"""A judging page for a round of captures: each page large, with yes / no for the page,
and its own materials beneath it, each with yes / no. Judging a page and judging its
typeface stay separate.

  python3 judge.py plate-2026-10-07-round-2      writes <data>/judge-<plate>.html

Marks are kept by serve.py in <data>/<plate>-marks.md (readable) and .json.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

from PIL import Image

import library as lib
import plate as plates

TOOL = Path(__file__).resolve().parent
DATA = lib.DATA


def page_materials(c, imgdir):
    out = []
    # typefaces, cut from this page (never a banner if the page has anything else)
    by = {}
    for b in c["blocks"]:
        by.setdefault(b["font"], []).append(b)
    for font, bs in by.items():
        if not font:
            continue
        fair = [b for b in bs if not lib.BANNER.search(b["text"]) and 0 <= b["y"] and b["y"] + b["h"] <= lib.H and b["h"] <= 240] or bs
        best = max(fair, key=lambda b: (min(b["size"], 60) * min(b["chars"], 40), b["w"]))
        im = Image.open(c["jpg"]).convert("RGB")
        box = (max(0, best["x"] - 6), max(0, best["y"] - 6), min(lib.W, best["x"] + min(best["w"], 720) + 6), min(lib.H, best["y"] + min(best["h"], 240) + 6))
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            continue
        f = imgdir / f"{lib.slug(c['stem'])}--type-{lib.slug(font)}.png"
        im.crop(box).save(f)
        out.append({"id": f"type:{lib.slug(font)}", "kind": "typeface", "label": font,
                    "detail": " ".join(map(str, sorted({round(b['size']) for b in bs}))) + " px", "img": str(f.relative_to(DATA))})
    # colours: the picture's ground and accents, and the text's ink
    im = Image.open(c["jpg"]).convert("RGB").resize((144, 90))
    px = list(im.getdata())
    q = Counter((r // 24, g // 24, b // 24) for r, g, b in px)
    seen = []
    for i, (bin_, n) in enumerate(q.most_common(8)):
        members = [p for p in px if (p[0] // 24, p[1] // 24, p[2] // 24) == bin_]
        rgb = tuple(round(sum(m[k] for m in members) / len(members)) for k in range(3))
        sat = (max(rgb) - min(rgb)) / 255
        role = "ground" if i == 0 else "accent" if sat > 0.35 and n / len(px) > 0.004 else None
        if role and all(sum((a - b) ** 2 for a, b in zip(rgb, s)) ** 0.5 > 36 for s in seen):
            seen.append(rgb)
            hexc = "#%02X%02X%02X" % rgb
            out.append({"id": f"colour:{hexc[1:].lower()}", "kind": "colour", "label": hexc, "detail": role, "hex": hexc})
    if c["blocks"]:
        s = plates.summarize(c["blocks"])
        for ink in s["ink"][:2]:
            if ink and all(o.get("hex") != ink for o in out):
                out.append({"id": f"colour:{ink[1:].lower()}", "kind": "colour", "label": ink, "detail": "ink", "hex": ink})
        out.append({"id": f"scale:{lib.slug(c['stem'])}", "kind": "scale", "label": f"{len(s['sizes'])} size{'s' if len(s['sizes']) > 1 else ''}",
                    "detail": " ".join(map(str, s["sizes"])) + " px", "sizes": s["sizes"]})
        out.append({"id": f"layout:{lib.slug(c['stem'])}", "kind": "layout", "label": "layout", "detail": f"{len(c['blocks'])} text blocks",
                    "img": f"library/img/layout-{lib.slug(c['stem'])}.png"})
    return out


def build(plate):
    imgdir = DATA / "library" / "img" / "pages"
    imgdir.mkdir(parents=True, exist_ok=True)
    cards = []
    for c in lib.captures():
        if not c["stem"].startswith(plate + "/"):
            continue
        cards.append({"stem": c["stem"], "name": c["name"], "url": c["url"],
                      "img": str(c["jpg"].relative_to(DATA)), "materials": page_materials(c, imgdir)})
    for i, c in enumerate(cards, 1):
        c["no"] = f"{i:02d}"
    tpl = (TOOL / "templates" / "judge.html").read_text()
    out = DATA / f"judge-{plate}.html"
    out.write_text(tpl.replace("/*CARDS*/[]", json.dumps(cards)).replace("{{PLATE}}", plate))
    print(f"{out.name}: {len(cards)} pages, {sum(len(c['materials']) for c in cards)} materials")


def marks_to_markdown(plate, marks):
    cards = {c["stem"]: c for c in marks.get("meta", [])}
    lines = [f"""---
type: notes
purpose: My yes and no on each page of {plate}, and on each of its materials, judged separately.
home: 00 Studio OS
private: yes
edits: both
created: 2026-10-07
updated: [2026-10-07]
---

# {plate}, judged

Kept by the judging page (http://127.0.0.1:8741/judge). A page's yes or no is about the page; a material's is about the material, in that page.
"""]
    for stem, m in sorted(marks.get("pages", {}).items(), key=lambda kv: cards.get(kv[0], {}).get("no", kv[0])):
        mats = {k: v for k, v in (m.get("materials") or {}).items() if v}
        if not m.get("page") and not mats and not (m.get("why") or "").strip():
            continue
        c = cards.get(stem, {})
        lines.append(f"## {c.get('no', '')} · {c.get('name', stem)} — {m.get('page') or 'no mark on the page'}")
        lines.append(c.get("url", ""))
        if (m.get("why") or "").strip():
            lines.append("- why: " + " ".join(m["why"].split()))
        for k, v in sorted(mats.items()):
            lines.append(f"- {v}: `{k}`")
        lines.append("")
    tmp = DATA / f"{plate}-marks.md.tmp"
    tmp.write_text("\n".join(lines))
    tmp.replace(DATA / f"{plate}-marks.md")


if __name__ == "__main__":
    build(sys.argv[1])
