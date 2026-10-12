#!/usr/bin/env python3
"""The library of materials: every captured page broken into the materials it's made of,
each kept with its provenance (where it came from, and my verdict on that source).

  python3 library.py        rebuilds the data folder's library/ from every capture

Deterministic: everything here is measured or cut from the captures, never written by a model.
New kinds of material (annotated photographs, motion, video) join by adding an extractor to KINDS.

A material:  id · kind · name · values · sources [{page, url, verdict, captured}] · image (a cut or a drawing)
Uses (what was made from which materials) are kept by hand or by agents in the data folder's library/uses.md.
"""
import json, re
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

import plate as plates

TOOL = Path(__file__).resolve().parent
from paths import DATA
LIB = DATA / "library"
W, H = 1440, 900


# ---------- the sources: every capture, with my verdict where I gave one ----------

def verdicts():
    """measured stem -> verdict, from sites-judged.md"""
    out = {}
    f = DATA / "sites-judged.md"
    if f.exists():
        for name, v, stem in re.findall(r"## (.+?) — (mine|some|kin|inspiration|not mine)\n\S+\nmeasured: (\S+)", f.read_text()):
            out[stem] = v
    return out


def captures():
    v = verdicts()
    out = []
    for j in sorted([j for d in sorted(DATA.glob("plate-*")) if d.is_dir() for j in d.glob("*.json")] + list((DATA / "walk-2026-10-07" / "measured").glob("*.json"))):
        stem = str(j.relative_to(DATA))[:-5]
        d = json.loads(j.read_text())
        jpg = j.with_suffix(".jpg")
        if not jpg.exists():
            continue
        out.append({"stem": stem, "name": d.get("name", stem), "url": d.get("asked_url", ""), "captured": d.get("captured", ""),
                    "verdict": v.get(stem, "unjudged"), "blocks": d.get("blocks", []), "space": d.get("space", {}), "jpg": jpg})
    return out


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50]


def src(c):
    return {"page": c["name"], "stem": c["stem"], "url": c["url"], "verdict": c["verdict"], "captured": c["captured"]}


# ---------- extractors, one per kind ----------

BANNER = re.compile(r"cookie|consent|privacy|subscribe|newsletter|sign up|log in|accept", re.I)


def typefaces(cs, cut):
    """One material per typeface, with a real cut of it from the page where it's used most."""
    by = defaultdict(list)
    for c in cs:
        for b in c["blocks"]:
            by[b["font"]].append((c, b))
    out = []
    for font, uses in by.items():
        if font in ("", "inherit"):
            continue
        srcs = {c["stem"]: c for c, _ in uses}
        sizes = sorted({round(b["size"]) for _, b in uses})
        weights = sorted({str(b["weight"]) for _, b in uses})
        # the specimen: the biggest legible block in this face, cut from its page (never a consent banner)
        fair = [cb for cb in uses if not BANNER.search(cb[1]["text"]) and cb[1]["y"] >= 0 and cb[1]["y"] + cb[1]["h"] <= H and cb[1]["h"] <= 240] or uses
        best = max(fair, key=lambda cb: (min(cb[1]["size"], 60) * min(cb[1]["chars"], 40), cb[1]["w"]))
        img = cut(best[0], best[1], f"type-{slug(font)}")
        out.append({"id": f"type:{slug(font)}", "kind": "typeface", "name": font,
                    "values": {"sizes": sizes, "weights": weights, "cases": sorted({b["case"] for _, b in uses if b.get("case") not in (None, "none")}),
                               "specimen": best[1]["text"][:40], "specimen_size": round(best[1]["size"])},
                    "sources": [src(c) for c in srcs.values()], "image": img})
    return out


def scales(cs, draw):
    """One material per page: the sizes it uses, and the steps between them."""
    out = []
    for c in cs:
        if not c["blocks"]:
            continue
        s = plates.summarize(c["blocks"])
        sizes = s["sizes"]
        steps = [round(b / a, 2) for a, b in zip(sizes, sizes[1:])]
        img = draw("scale", c, sizes)
        out.append({"id": f"scale:{slug(c['stem'])}", "kind": "scale", "name": f"{len(sizes)} size{'s' if len(sizes) > 1 else ''}, body {s['body']}",
                    "values": {"sizes": sizes, "body": s["body"], "steps": steps, "largest_over_body": s["largest_over_body"]},
                    "sources": [src(c)], "image": img})
    return out


def lum(rgb):
    r, g, b = (v / 255 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def colours(cs, _):
    """Colours by role, read from the picture (ground, accents) and from the text (ink)."""
    found = defaultdict(lambda: {"roles": set(), "sources": {}})
    for c in cs:
        im = Image.open(c["jpg"]).convert("RGB").resize((144, 90))
        px = list(im.getdata())
        q = Counter((r // 24, g // 24, b // 24) for r, g, b in px)
        ranked = q.most_common(8)
        for i, (bin_, n) in enumerate(ranked):
            members = [p for p in px if (p[0] // 24, p[1] // 24, p[2] // 24) == bin_]
            rgb = tuple(round(sum(m[k] for m in members) / len(members)) for k in range(3))
            share = n / len(px)
            sat = (max(rgb) - min(rgb)) / 255
            role = "ground" if i == 0 else "accent" if sat > 0.35 and share > 0.004 else None
            if role:
                hexc = "#%02X%02X%02X" % rgb
                found[hexc]["roles"].add(role)
                found[hexc]["sources"][c["stem"]] = c
        for b in c["blocks"]:
            hexc = plates.rgb_hex(b["color"])
            if hexc and b["chars"] > 20:
                found[hexc]["roles"].add("ink")
                found[hexc]["sources"][c["stem"]] = c
    # merge colours that sit close together; the most-used one names the group
    rgbs = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    order = sorted(found, key=lambda h: -len(found[h]["sources"]))
    merged = {}
    for h in order:
        home = next((k for k in merged if sum((a - b) ** 2 for a, b in zip(rgbs(h), rgbs(k))) ** 0.5 < 36), None)
        if home:
            merged[home]["roles"] |= found[h]["roles"]; merged[home]["sources"].update(found[h]["sources"]); merged[home]["also"].append(h)
        else:
            merged[h] = {"roles": set(found[h]["roles"]), "sources": dict(found[h]["sources"]), "also": []}
    found = merged
    out = []
    for hexc, f in found.items():
        out.append({"id": f"colour:{hexc[1:].lower()}", "kind": "colour", "name": hexc,
                    "values": {"hex": hexc, "roles": sorted(f["roles"]), "near": f["also"][:4]},
                    "sources": [src(c) for c in f["sources"].values()], "image": None})
    out.sort(key=lambda m: (-len(m["sources"]), m["name"]))
    return out


def spacings(cs, _):
    """One material per page: the spacing values it repeats most."""
    out = []
    for c in cs:
        if not c["space"]:
            continue
        top = [int(k) for k, _ in sorted(c["space"].items(), key=lambda kv: -kv[1])[:6]]
        out.append({"id": f"spacing:{slug(c['stem'])}", "kind": "spacing", "name": " ".join(map(str, sorted(top))) + " px",
                    "values": {"steps": sorted(top)}, "sources": [src(c)], "image": None})
    return out


def layouts(cs, draw):
    """One material per page: its first screen reduced to the boxes of its text (a skeleton)."""
    out = []
    for c in cs:
        if not c["blocks"]:
            continue
        img = draw("layout", c, None)
        xs = sorted({round(b["x"] / 48) * 48 for b in c["blocks"] if b["chars"] > 20})
        out.append({"id": f"layout:{slug(c['stem'])}", "kind": "layout", "name": c["name"],
                    "values": {"text_columns_from_left_px": xs[:6], "blocks": len(c["blocks"])},
                    "sources": [src(c)], "image": img})
    return out


KINDS = [("typeface", typefaces), ("scale", scales), ("colour", colours), ("spacing", spacings), ("layout", layouts)]


# ---------- drawing and cutting ----------

def make_cutter(imgdir):
    def cut(c, b, name):
        im = Image.open(c["jpg"]).convert("RGB")
        pad = 6
        box = (max(0, b["x"] - pad), max(0, b["y"] - pad), min(W, b["x"] + min(b["w"], 720) + pad), min(H, b["y"] + min(b["h"], 240) + pad))
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            return None
        f = imgdir / f"{name}.png"
        im.crop(box).save(f)
        return str(f.relative_to(DATA))
    return cut


def make_drawer(imgdir):
    def draw(kind, c, sizes):
        if kind == "layout":
            im = Image.new("RGB", (W // 4, H // 4), "white")
            d = ImageDraw.Draw(im)
            for b in c["blocks"]:
                x, y, w, h = b["x"] / 4, b["y"] / 4, max(b["w"] / 4, 1), max(b["h"] / 4, 1)
                shade = 0 if b["size"] >= 24 else 90 if b["chars"] > 20 else 160
                d.rectangle([x, y, x + w, y + h], fill=(shade, shade, shade))
            f = imgdir / f"layout-{slug(c['stem'])}.png"
        else:
            im = Image.new("RGB", (360, 70), "white")
            d = ImageDraw.Draw(im)
            x = 6
            top = max(sizes)
            for s in sizes:
                h = max(2, round(56 * s / top))
                d.rectangle([x, 64 - h, x + 8, 64], fill=(0, 0, 0))
                x += 14
            f = imgdir / f"scale-{slug(c['stem'])}.png"
        im.save(f)
        return str(f.relative_to(DATA))
    return draw


def uses():
    """What was made from which materials: lines like '- 2026-10-08 · test-2 · type:helvetica, colour:ffef00'."""
    f = LIB / "uses.md"
    out = defaultdict(list)
    if f.exists():
        for date, made, ids in re.findall(r"^- (\S+) · (.+?) · (.+)$", f.read_text(), re.M):
            for i in [x.strip() for x in ids.split(",")]:
                out[i].append({"date": date, "made": made})
    return out


def build():
    imgdir = LIB / "img"
    imgdir.mkdir(parents=True, exist_ok=True)
    for old in imgdir.glob("*.png"):
        old.unlink()
    cs = captures()
    cut, draw = make_cutter(imgdir), make_drawer(imgdir)
    materials = []
    for kind, fn in KINDS:
        materials += fn(cs, cut if kind == "typeface" else draw)
    u = uses()
    for m in materials:
        m["uses"] = u.get(m["id"], [])
    (LIB / "materials.json").write_text(json.dumps(materials, indent=1))
    write_index(materials, cs)
    if not (LIB / "uses.md").exists():
        (LIB / "uses.md").write_text(USES_HEADER)
    return materials


USES_HEADER = """---
type: record
purpose: What was made from which materials in the library: the lineage of each material. One line per thing made.
home: 00 Studio OS
private: yes
edits: both
created: 2026-10-07
updated: [2026-10-07]
---

# Uses

One line per thing made from the library: the date, what was made (and where it lives), and the ids of the materials it pulled, comma-separated.
Agents add a line whenever they make something from the library.

"""


def write_index(materials, cs):
    lines = ["""---
type: reference
purpose: The library of materials, as text: every material cut or measured from my captures, with its provenance. Rebuilt by tools/physiognomy/library.py; don't edit by hand.
home: 00 Studio OS
private: yes
edits: agents
created: 2026-10-07
updated: [2026-10-07]
---

# The library of materials
""", f"From {len(cs)} captured pages. Each material keeps where it came from and my verdict on that source (mine, some, kin, inspiration, not mine, or unjudged).",
             "A verdict belongs to the source, not the material: a typeface from a page I called too much can still be mine in another arrangement.", ""]
    for kind, _ in KINDS:
        ms = [m for m in materials if m["kind"] == kind]
        lines.append(f"## {kind}s ({len(ms)})\n")
        for m in ms:
            where = "; ".join(f"{s['page']} ({s['verdict']})" for s in m["sources"])
            vals = ", ".join(f"{k} {v if not isinstance(v, list) else ' '.join(map(str, v))}" for k, v in m["values"].items() if v not in ([], "", None))
            lines.append(f"- `{m['id']}` **{m['name']}**: {vals}. From: {where}.")
        lines.append("")
    (LIB / "library.md").write_text("\n".join(lines))


if __name__ == "__main__":
    ms = build()
    print(Counter(m["kind"] for m in ms))
