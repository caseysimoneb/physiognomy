#!/usr/bin/env python3
"""What the taste tool's view shows, read fresh from the data folder (paths.py) each time.

Facts come from code: the marks, the verdicts, the measured values. The paragraph for each
verdict is assembled from those numbers by code (no model), and describes ranges and what
recurs, not an average.
"""
import html, json, re
from collections import Counter
from pathlib import Path
from statistics import median

import plate as plates

try:
    from PIL import Image
except ImportError:  # the picture-based ground is skipped without Pillow
    Image = None


def picture_ground(jpg):
    """The colour covering most of the captured first screen, read from the picture."""
    if Image is None or not jpg.exists():
        return None
    im = Image.open(jpg).convert("RGB").resize((144, 90))
    px = list(im.getdata())
    q = Counter((r // 12, g // 12, b // 12) for r, g, b in px)
    top = q.most_common(1)[0][0]
    members = [p for p in px if (p[0] // 12, p[1] // 12, p[2] // 12) == top]
    r, g, b = (round(sum(c[i] for c in members) / len(members)) for i in range(3))
    return "#%02X%02X%02X" % (r, g, b)

TOOL = Path(__file__).resolve().parent
from paths import DATA
ORDER = ["mine", "some", "kin", "inspiration", "not mine"]
ABOUT = {
    "mine": "what I'd make",
    "some": "a part of it is mine",
    "kin": "I admire the thinking, not the look",
    "inspiration": "a place to get ideas, not a model",
    "not mine": "the edges",
}


def pins():
    out, kind = [], None
    f = DATA / "board-marks.md"
    if not f.exists():
        return out
    for line in f.read_text().splitlines():
        if line.startswith("## for "):
            kind = {"the look": "look", "the idea": "idea", "both": "both"}.get(line[7:].split(" (")[0].strip())
        m = re.match(r"^- (\d{3}) · (.*?) · (\S+)$", line)
        if m and kind:
            out.append({"n": m[1], "group": m[2], "url": m[3], "k": kind})
    return out


def sites():
    f = DATA / "sites-judged.md"
    if not f.exists():
        return []
    out = []
    for block in re.split(r"\n(?=## )", f.read_text()):
        m = re.match(r"## (.+?) — (mine|some|kin|inspiration|not mine)\n(\S+)\nmeasured: (\S+)\n(.*)", block, re.S)
        if not m:
            continue
        stem = m[4]
        facts = {}
        j = DATA / f"{stem}.json"
        if j.exists():
            d = json.loads(j.read_text())
            facts = plates.summarize(d.get("blocks", []), d.get("space"))
            facts["measure_px"] = [round(w) for w in d.get("measure_px", [])][:2]
            pg = picture_ground(DATA / f"{stem}.jpg")
            if pg:
                facts["ground"] = [pg]
        img = stem + ".jpg" if (DATA / f"{stem}.jpg").exists() else None
        notes = [l[2:].strip() for l in m[5].splitlines() if l.startswith("- ")]
        out.append({"name": m[1], "verdict": m[2], "url": m[3], "img": img, "facts": facts, "notes": notes})
    return out


def lum(hexc):
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def sat(hexc):
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b)


def paragraph(group):
    """One paragraph per verdict, from the numbers only."""
    fs = [s["facts"] for s in group if s["facts"].get("sizes")]
    if not fs:
        return "Nothing measured here yet."
    n = len(fs)
    counts = sorted(len(f["sizes"]) for f in fs)
    bodies = sorted(f["body"] for f in fs)
    ratios = sorted(f["largest_over_body"] for f in fs if f.get("largest_over_body"))
    fonts = Counter(font for f in fs for font in f["fonts"][:1])
    grounds = [f["ground"][0] for f in fs if f.get("ground")]
    light = sum(1 for g in grounds if lum(g) > 0.8)
    accents = [c for f in fs for c in f.get("ink", [])[:2] if sat(c) > 0.35]
    spacing = Counter(v for f in fs for v in f.get("spacing", [])[:3])
    one_size = sum(1 for c in counts if c <= 2)
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    w = lambda k: words.get(k, str(k))
    rng = lambda a, b, unit="": f"{a:g}{unit}" if a == b else f"{a:g} to {b:g}{unit}"
    parts = [f"{w(n).capitalize()} measured page{'s' if n > 1 else ''}."]
    if counts[0] == counts[-1]:
        parts.append(f"Type is set in {w(counts[0])} size{'s' if counts[0] > 1 else ''}.")
    else:
        parts.append(f"Type is set in {w(counts[0])} to {w(counts[-1])} sizes" + (f" (median {median(counts):g})" if n > 2 else "") + "; "
                     + (f"{w(one_size)} of {w(n)} use{'s' if one_size == 1 else ''} one or two" if one_size else "none uses fewer than three") + ".")
    parts.append(f"Body text is {rng(bodies[0], bodies[-1], ' px')}.")
    if ratios and ratios[-1] > 1:
        parts.append(f"The largest type is {rng(ratios[0], ratios[-1], '×')} the body.")
    elif ratios:
        parts.append("Nothing is set larger than the body.")
    parts.append("Typefaces: " + ", ".join(k for k, _ in fonts.most_common(4)) + ".")
    if grounds:
        parts.append(("All sit" if light == len(grounds) else f"{w(light).capitalize()} of {w(len(grounds))} sit") + " on a light ground"
                     + ("" if light == len(grounds) else f"; {w(len(grounds) - light)} on a dark or coloured one") + ".")
    acc = sorted(set(accents))
    parts.append("No saturated colour in the text." if not acc else f"Saturated colour in the text: {', '.join(acc[:4])}.")
    if spacing:
        parts.append("Spacing that recurs: " + ", ".join(f"{k}" for k, _ in spacing.most_common(4)) + " px.")
    return " ".join(parts)


def md_to_html(text):
    """Enough Markdown for the profile: headings, lists, paragraphs, bold, italic, code, links."""
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    out, para, lst = [], [], []

    def inline(s):
        s = html.escape(s, quote=False)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        s = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", s)
        return s

    def flush():
        if para:
            out.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>")
            para.clear()
        if lst:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in lst) + "</ul>")
            lst.clear()

    for line in text.splitlines():
        h = re.match(r"^(#{1,3}) (.+)", line)
        if h:
            flush()
            out.append(f"<h{len(h[1]) + 1}>{inline(h[2])}</h{len(h[1]) + 1}>")
        elif line.startswith("- "):
            if para:
                flush()
            lst.append(line[2:])
        elif line.startswith("  ") and lst:
            lst[-1] += " " + line.strip()
        elif not line.strip():
            flush()
        else:
            if lst:
                flush()
            para.append(line)
    flush()
    return "\n".join(out)


def judged_pages():
    """Every captured page I marked: yes or no on the page, or only on some of its materials. My words where I gave them."""
    import library as lib
    from nearness import page_marks
    marks = page_marks()
    matmarks = {}
    for f in DATA.glob("plate-*-marks.json"):
        for stem, m in json.loads(f.read_text()).get("pages", {}).items():
            ms = {k: v for k, v in (m.get("materials") or {}).items() if v}
            if ms:
                matmarks[stem] = ms
    words = {}
    f = DATA / "sites-judged.md"
    if f.exists():
        for name, v, url, stem, rest in re.findall(r"## (.+?) — (mine|some|kin|inspiration|not mine)\n(\S+)\nmeasured: (\S+)\n(.*?)(?=\n## |\Z)", f.read_text(), re.S):
            words[stem] = [l[2:].strip() for l in rest.splitlines() if l.startswith("- ")]
    out = []
    for c in lib.captures():
        mark = marks.get(c["stem"], "")
        ms = matmarks.get(c["stem"], {})
        if not mark and not ms:
            continue
        facts = plates.summarize(c["blocks"], c["space"]) if c["blocks"] else {}
        pg = picture_ground(c["jpg"])
        if pg:
            facts["ground"] = [pg]
        out.append({"name": c["name"], "url": c["url"], "mark": mark or "materials only",
                    "img": str(c["jpg"].relative_to(DATA)), "facts": facts, "notes": words.get(c["stem"], []),
                    "materials": [f"{v}: {k.split(':', 1)[0]}" + ("" if k.split(':', 1)[0] in ("scale", "layout") else " " + (("#" + k.split(':', 1)[1].upper()) if k.startswith("colour:") else k.split(':', 1)[1].replace("-", " "))) for k, v in ms.items()]})
    return out


def tests():
    out = []
    for d in sorted(DATA.glob("test-*")):
        key_f, v_f = d / "key.json", d / "verdict.json"
        if not key_f.exists():
            continue
        key = json.loads(key_f.read_text())
        v = json.loads(v_f.read_text()) if v_f.exists() else {}
        who = {"x-profile.html": "made from my profile", "x-pulled.html": "pulled from my library", "x-default.html": "Claude's habits"}
        chose = who.get(key.get(v.get("verdict"), ""), "") if v.get("verdict") in ("i", "ii") else ""
        out.append({"name": d.name, "chose": chose, "why": v.get("why", ""),
                    "files": [{"label": who.get(x, x), "href": f"/tests/{d.name}/{x}"} for x in sorted(set(key.values()))] if v.get("revealed") or chose else []})
    return out


def data():
    ps = judged_pages()
    groups = []
    for v, about in (("yes", "pages I said yes to"), ("materials only", "pages where I marked only some materials"), ("no", "pages I said no to")):
        g = [p for p in ps if p["mark"] == v]
        if g:
            groups.append({"verdict": v, "about": about, "sites": g, "paragraph": paragraph(g)})
    verdict = {}
    vf = DATA / "test-2026-10-07" / "verdict.json"
    if vf.exists():
        verdict = json.loads(vf.read_text())
        key = json.loads((DATA / "test-2026-10-07" / "key.json").read_text())
        verdict["chose"] = {"x-profile.html": "the page made from my profile", "x-default.html": "the page from Claude's habits"}.get(key.get(verdict.get("verdict"), ""), verdict.get("verdict"))
    profile = DATA / "profile.md"
    lib = DATA / "library" / "materials.json"
    pulled = DATA / "library" / "pulled.md"
    return {"pins": pins(), "groups": groups,
            "library": json.loads(lib.read_text()) if lib.exists() else [],
            "pulled": re.findall(r"^- `([^`]+)`", pulled.read_text(), re.M) if pulled.exists() else [],
            "profile": md_to_html(profile.read_text()) if profile.exists() else "",
            "tests": tests()}


if __name__ == "__main__":
    d = data()
    print(len(d["pins"]), "pins;", sum(len(g["sites"]) for g in d["groups"]), "sites")
    for g in d["groups"]:
        print(g["verdict"], "—", g["paragraph"])
