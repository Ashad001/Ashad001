#!/usr/bin/env python3
"""Render the profile card: ASCII art on the left, neofetch-style rows on the
right, as one SVG per theme. GitHub markdown has no color in code blocks, so
the card is an SVG the README embeds via <picture>.

Everything is laid out on a monospace character grid, so dot leaders line up
without measuring glyphs.

Usage:
  python3 scripts/build_card.py                 # portrait art (assets/photo-ascii.txt)
  python3 scripts/build_card.py --art cube      # animated rotating 3D cube
  python3 scripts/build_card.py --anim          # stagger the rows in (see note)

--anim renders blank in viewers that snapshot SMIL at t=0 (macOS quicklook,
some social previews), so the rows are static unless asked for. The cube's
frame 0 is a static group, so it degrades to a still frame instead.
Reads assets/stats.json (written by fetch_stats.py) when present.
"""
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ART = REPO / "assets" / "photo-ascii.txt"
SPRITE = REPO / "assets" / "bravo.png"
STATS = REPO / "assets" / "stats.json"

# --- content -----------------------------------------------------------------
HEADER = "ashad@imagine"
SECTIONS = [
    (None, [
        ("Role", "Engineer turned Product Manager & Founder"),
        ("Company", "ImagineArt (Vyro)"),
        ("Location", "Islamabad, Pakistan"),
        ("Shipped", "Plugins, Agents, Harness"),
        ("Now", "Shipping in day, researching as a bat duty"),
        ("Editor", "SuperSet, Claude Code, Hermes"),
    ]),
    (None, [
        ("Stack.Languages", "Python, Rust, TypeScript, Go"),
        ("Stack.Runtimes", "Adobe UXP/CEP, Electron, MCP"),
        ("Stack.Agents", "LangGraph, LangSmith, Hermes"),
        ("Stack.Data", "Postgres, DuckDB, Redis, pgvector"),
    ]),
    (None, [
        ("Building.Product", "ImagineArt plugins, ImagineArt Extension"),
        ("Building.OSS", "Superset fork, claude-arcade, Fyltr, BoltSQL"),
    ]),
    ("Contact", [
        ("Email", "ashad001sp@gmail.com"),
        ("LinkedIn", "in/ashadqureshi1"),
        ("X", "@ashadqu7"),
        ("Site", "ashadabdullah.com"),
    ]),
]

# --- themes ------------------------------------------------------------------
THEMES = {
    "dark":  dict(page="#0d1117", card="#161b22", key="#E8A33D", val="#79c0ff",
                  dots="#30363d", rule="#484f58", art="#8b949e", head="#e6edf3"),
    "light": dict(page="#ffffff", card="#f6f8fa", key="#bf8700", val="#0969da",
                  dots="#d0d7de", rule="#8c959f", art="#57606a", head="#1f2328"),
}

COLS = 60          # character columns in the right panel
FS = 13            # right panel font size
LH = 19.5          # right panel line height
ART_FS = 11.5      # art font size
ART_LH = 11.5
PAD = 26
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
CW = 0.6           # monospace advance as a fraction of font size


def esc(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # numeric refs keep the SVG ASCII-only, so it survives being inlined into a
    # page whose charset we do not control
    return "".join(c if ord(c) < 128 else f"&#{ord(c)};" for c in s)


def rule_row(title):
    """`- Title ------------------` filling the panel width."""
    if title is None:
        return None
    head = f"- {title} "
    return head + "-" * max(0, COLS - len(head))


def leader_row(key, value):
    """`. key: ....... value` with the value flush right on the grid."""
    left = f". {key}: "
    gap = COLS - len(left) - len(value) - 2
    if gap < 1:                      # value too long: drop the leader
        return f"{left}{value}", len(left), None
    return f"{left} {'.' * gap} {value}", len(left), COLS - len(value)


def stats_rows():
    if not STATS.exists():
        return []
    s = json.loads(STATS.read_text())
    rows = [
        ("Repos", f"{s['public_repos']}  |  Stars: {s['total_stars']}"),
        ("Followers", f"{s['followers']}  |  Commits (YTD): {s.get('commits_ytd', '-')}"),
        ("Streak", f"{s.get('current_streak', '-')} days  |  longest {s.get('longest_streak', '-')}"),
        ("Top languages", s.get("top_languages", "-")),
        ("Most starred", s.get("most_starred", "-")),
    ]
    return [("GitHub Stats", rows)]


# --- ASCII art ---------------------------------------------------------------
def portrait():
    lines = ART.read_text().rstrip("\n").split("\n") if ART.exists() else ["(no art)"]
    return [[[(line, None)] for line in lines]]        # single frame, one run per row


# sprite palette -> theme token, so the black outline stays visible on both grounds
SPRITE_PALETTE = {
    (0, 0, 0): "ink", (24, 24, 24): "ink", (40, 40, 40): "ink",
    (247, 183, 15): "hair", (247, 143, 92): "skin",
    (222, 143, 105): "skin", (250, 173, 137): "skin", (56, 92, 254): "denim",
}
# the shirt and the sunglasses are the same black in the source, but the shirt
# has to stay visible on a dark card while the glasses have to read as black.
# They are separable by height: the glasses are the band above the face.
SPRITE_COLORS = {
    "dark":  {"ink": "#c9d1d9", "glass": "#05070a", "hair": "#f7b70f",
              "skin": "#f78f5c", "denim": "#6b8cff"},
    "light": {"ink": "#1f2328", "glass": "#05070a", "hair": "#c98a00",
              "skin": "#e2703a", "denim": "#385cfe"},
}
GLASSES_BELOW = 132             # source y under which black is shirt, not lens
# the wave is posed, not swung: the hand block travels up the side of the body
# and a forearm is drawn in behind it, so the torso never moves.
HAND = (225, 224, 239, 251)      # the skin block at the shirt hem
ELBOW = (247, 212)               # where the forearm leaves the sleeve
HEM = 238                        # shirt ends / white background starts
LIFT, DRIFT = 54, 5              # how far the hand travels up and outward
GREETING = "Hey there, good lookin'."   # in a bubble, only while the hand is up
RAMP = " .:-=+*#%@"


def _put(frame, row, col, text, key):
    """Overwrite cells in one frame row with coloured text."""
    if not 0 <= row < len(frame):
        return
    chars = list("".join(t for t, _ in frame[row]))
    keys = [k for t, k in frame[row] for _ in t]
    pad = col + len(text) - len(chars)
    if pad > 0:
        chars += [" "] * pad
        keys += [None] * pad
    chars[col:col + len(text)] = list(text)
    keys[col:col + len(text)] = [key] * len(text)
    runs, run, cur = [], "", keys[0] if keys else None
    for ch, k in zip(chars, keys):
        if k != cur and run:
            runs.append((run, cur)); run = ""
        cur, run = k, run + ch
    if run:
        runs.append((run, cur))
    frame[row] = runs


def sprite_frames(frames=32, cols=48):
    """Pixel sprite as colored ASCII, raising a hand to say hi.

    The body is fixed - only the hand block moves, with a forearm drawn from the
    sleeve to wherever it currently is. Lift and wiggle are sine terms over one
    period, so frame N-1 hands back to frame 0 with nothing to jump.
    """
    from PIL import ImageDraw
    from PIL import Image

    img = Image.open(SPRITE).convert("RGBA")
    flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flat.alpha_composite(img)
    img = flat.convert("RGB")
    box = (125, 25, 263, 300)                       # character bounds, whitespace trimmed
    pad = 4
    rows_n = int(cols * (box[3] - box[1]) / (box[2] - box[0]) * 0.5)

    hand = img.crop(HAND)
    skin = (247, 143, 92)

    out = []
    for f in range(frames):
        t = 2 * math.pi * f / frames
        lift = max(0.0, math.sin(t)) ** 2             # rests half the loop, no seam
        wiggle = 5 * math.sin(3 * t) * lift           # only wiggles once raised
        hx = HAND[0] + DRIFT * lift + wiggle
        hy = HAND[1] - LIFT * lift

        posed = img.copy()
        posed.paste((0, 0, 0), (HAND[0], HAND[1], HAND[2], HEM))     # shirt behind
        posed.paste((255, 255, 255), (HAND[0], HEM, HAND[2], HAND[3]))
        if lift > 0.02:                               # forearm follows the hand
            # the forearm reads as raised in front of the shirt, like the sprite
            ImageDraw.Draw(posed).line(
                [ELBOW, (hx + (HAND[2] - HAND[0]) / 2, hy + 14)],
                fill=skin, width=9)
        posed.paste(hand, (round(hx), round(hy)))

        crop = posed.crop((box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad))
        crop = crop.transpose(Image.FLIP_LEFT_RIGHT)      # face the stats column
        # density comes from how much of the cell the sprite covers, and colour
        # from which material dominates it - luminance alone made the bright
        # amber hair render sparser than the black shirt
        px = crop.load()
        # same cut line, expressed in this frame's crop coordinates
        glass_cut = GLASSES_BELOW - (box[1] - pad)
        mats = list(dict.fromkeys(SPRITE_PALETTE.values())) + ["glass"]
        masks = {m: Image.new("L", crop.size, 0) for m in mats}
        cover = Image.new("L", crop.size, 0)
        mp, cp = {m: masks[m].load() for m in mats}, cover.load()
        for y in range(crop.height):
            for x in range(crop.width):
                r, g, b = px[x, y]
                if r > 232 and g > 232 and b > 232:
                    continue
                key = min(SPRITE_PALETTE, key=lambda c: (c[0]-r)**2 + (c[1]-g)**2 + (c[2]-b)**2)
                mat = SPRITE_PALETTE[key]
                if mat == "ink" and y < glass_cut:
                    mat = "glass"
                mp[mat][x, y] = 255
                cp[x, y] = 255
        cover = cover.resize((cols, rows_n), Image.BOX).load()
        small = {m: masks[m].resize((cols, rows_n), Image.BOX).load() for m in mats}

        frame = []
        for y in range(rows_n):
            runs, run, color = [], "", None
            for x in range(cols):
                c = cover[x, y]
                ch = RAMP[c * (len(RAMP) - 1) // 255]
                key = max(mats, key=lambda m: small[m][x, y]) if ch != " " else None
                if key != color and run:
                    runs.append((run, color)); run = ""
                color, run = key, run + ch
            if run:
                runs.append((run, color))
            frame.append(runs)

        # room above the sprite for a speech bubble, clear of the body
        frame = [[] for _ in range(4)] + frame
        if lift > 0.45:                               # only while the hand is up
            inner = len(GREETING) + 2
            _put(frame, 0, 1, "," + "-" * inner + ".", "ink")
            _put(frame, 1, 1, "|", "ink")
            _put(frame, 1, 3, GREETING, "hair")
            _put(frame, 1, 2 + inner, "|", "ink")
            _put(frame, 2, 1, "`" + "-" * inner + "'", "ink")
            _put(frame, 3, inner - 1, "\\", "ink")   # tail, pointing at his head
        out.append(frame)

    # trim padding that is blank in EVERY frame: dead rows top/bottom, and the
    # common indent. Per-frame trimming would cancel out the motion.
    def rows_text(frame):
        return ["".join(t for t, _ in row) for row in frame]

    texts = [rows_text(f) for f in out]
    live = [i for i in range(len(out[0]))
            if any(t[i].strip() for t in texts)]
    top, bottom = live[0], live[-1] + 1
    indent = min(len(t[i]) - len(t[i].lstrip(" "))
                 for t in texts for i in range(top, bottom) if t[i].strip())

    trimmed = []
    for frame in out:
        rows = []
        for row in frame[top:bottom]:
            drop, kept = indent, []
            for text, key in row:
                if drop:
                    cut = min(drop, len(text))
                    text, drop = text[cut:], drop - cut
                if text:
                    kept.append((text, key))
            if kept:                                   # rstrip the last run
                text, key = kept[-1]
                kept[-1] = (text.rstrip(), key)
            rows.append([r for r in kept if r[0]])
        trimmed.append(rows)
    return trimmed


CUBE = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
EDGES = [(a, b) for a in range(8) for b in range(a + 1, 8)
         if sum(1 for i in range(3) if CUBE[a][i] != CUBE[b][i]) == 1]
SHADE = "·:-=+*#%@"


def cube_frames(frames=30, w=52, h=30):
    """Wireframe cube rotating on two axes, depth-shaded, as text frames."""
    out = []
    for f in range(frames):
        a = 2 * math.pi * f / frames
        b = 2 * a + 0.4          # 2 turns per loop -> seamless wrap
        grid = [[" "] * w for _ in range(h)]
        for i, j in EDGES:
            p, q = CUBE[i], CUBE[j]
            for t in range(0, 91):
                s = t / 90
                x, y, z = (p[k] + (q[k] - p[k]) * s for k in range(3))
                # rotate Y then X
                x, z = x * math.cos(a) - z * math.sin(a), x * math.sin(a) + z * math.cos(a)
                y, z = y * math.cos(b) - z * math.sin(b), y * math.sin(b) + z * math.cos(b)
                d = 4 / (4 + z)                        # perspective
                cx, cy = int(w / 2 + x * d * w * 0.30), int(h / 2 - y * d * h * 0.42)
                if 0 <= cx < w and 0 <= cy < h:
                    grid[cy][cx] = SHADE[min(len(SHADE) - 1, int((z + 1.8) / 3.6 * len(SHADE)))]
        out.append([[("".join(row).rstrip(), None)] for row in grid])
    return out


# --- SVG ---------------------------------------------------------------------
def art_block(frames, x, y, color, palette=None):
    """Draw the art. Rows that never change are emitted once; only the rows that
    actually differ between frames get a copy per frame plus the opacity
    animation that cycles them. The body is static, so this is most of the art.
    """
    n = len(frames)
    height = max(len(f) for f in frames)

    def row_svg(runs, i):
        text = "".join(t for t, _ in runs)
        if not text.strip():
            return ""
        spans = "".join(
            esc(t) if not (key and palette)
            else f'<tspan fill="{palette[key]}">{esc(t)}</tspan>'
            for t, key in runs)
        return (f'<text x="{x}" y="{y + i * ART_LH:.1f}" xml:space="preserve" '
                f'textLength="{len(text) * ART_FS * CW:.1f}" lengthAdjust="spacing">'
                f'{spans}</text>')

    def row(f, i):
        return frames[f][i] if i < len(frames[f]) else []

    static, moving = [], []
    for i in range(height):
        if all(row(f, i) == row(0, i) for f in range(1, n)):
            static.append(row_svg(row(0, i), i))
        else:
            moving.append(i)

    out = [f'<g fill="{color}" font-size="{ART_FS}" font-family="{MONO}">'
           f'{"".join(static)}</g>']

    for f in range(n):
        rows = "".join(row_svg(row(f, i), i) for i in moving)
        if not rows:
            continue
        anim = ""
        if n > 1:
            first = "1" if f == 0 else "0"
            vals = ";".join("1" if i == f else "0" for i in range(n)) + f";{first}"
            times = ";".join(f"{i / n:.4f}" for i in range(n)) + ";1"
            anim = (f'<animate attributeName="opacity" dur="{n / 12:.1f}s" '
                    f'repeatCount="indefinite" calcMode="discrete" '
                    f'values="{vals}" keyTimes="{times}"/>')
        out.append(f'<g opacity="{1 if f == 0 else 0}" fill="{color}" '
                   f'font-size="{ART_FS}" font-family="{MONO}">{rows}{anim}</g>')
    return "".join(out)


def panel_rows(sections, x, y, t, animate=True):
    """Right panel: header, section rules, and key/value rows with leaders."""
    out, row = [], 0

    def text(content, dy_row, fill, extra="", cols=COLS):
        return (f'<text x="{x}" y="{y + dy_row * LH:.1f}" fill="{fill}" '
                f'xml:space="preserve" textLength="{cols * FS * CW:.1f}" '
                f'lengthAdjust="spacing"{extra}>{content}</text>')

    head = HEADER + " " + "-" * max(0, COLS - len(HEADER) - 1)
    out.append(text(f'<tspan fill="{t["head"]}">{esc(HEADER)}</tspan>'
                    f'<tspan fill="{t["rule"]}">{esc(head[len(HEADER):])}</tspan>',
                    row, t["head"]))
    row += 1

    for title, rows in sections:
        if title is not None:
            row += 1
            out.append(text(esc(rule_row(title)), row, t["rule"]))
        for key, value in rows:
            row += 1
            line, klen, vstart = leader_row(key, str(value))
            spans = [f'<tspan fill="{t["key"]}">{esc(line[:klen])}</tspan>']
            if vstart is None:
                spans.append(f'<tspan fill="{t["val"]}">{esc(line[klen:])}</tspan>')
            else:
                spans.append(f'<tspan fill="{t["dots"]}">{esc(line[klen:vstart])}</tspan>')
                spans.append(f'<tspan fill="{t["val"]}">{esc(line[vstart:])}</tspan>')
            fade = ""
            if animate:
                total = 2.6
                t1, t2 = row * 0.07 / total, (row * 0.07 + 0.3) / total
                fade = (f'<animate attributeName="opacity" dur="{total}s" '
                        f'values="0;0;1;1" keyTimes="0;{t1:.4f};{t2:.4f};1" '
                        f'fill="freeze"/>')
            out.append(text("".join(spans) + fade, row, t["key"]))
        row += 1
    return "".join(out), row


def build(theme_name, frames, sections, animate, palette=None):
    t = THEMES[theme_name]
    art_cols = max(sum(len(txt) for txt, _ in row) for f in frames for row in f)
    art_w = art_cols * ART_FS * CW
    art_h = max(len(f) for f in frames) * ART_LH
    body, rows = panel_rows(sections, 0, 0, t, animate)   # measure rows first
    panel_h = rows * LH
    inner_h = max(art_h, panel_h)
    w = int(PAD * 2 + art_w + 34 + COLS * FS * CW)
    h = int(PAD * 2 + inner_h)

    panel_w = COLS * FS * CW
    px, py = PAD, PAD + (inner_h - panel_h) / 2 + FS
    art_x = PAD + panel_w + 34
    art_y = PAD + (inner_h - art_h) / 2 + ART_FS
    body, _ = panel_rows(sections, px, py, t, animate)

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{MONO}" font-size="{FS}">'
            f'<rect width="{w}" height="{h}" rx="10" fill="{t["card"]}"/>'
            f'{art_block(frames, art_x, art_y, t["art"], palette)}'
            f'{body}</svg>')


def main():
    art = "sprite"
    for name in ("cube", "portrait", "sprite"):
        if name in sys.argv:
            art = name
    frames = {"cube": cube_frames, "portrait": portrait, "sprite": sprite_frames}[art]()
    animate = "--anim" in sys.argv
    sections = SECTIONS + stats_rows()
    suffix = {"sprite": "", "cube": "-cube", "portrait": "-portrait"}[art]
    for theme in THEMES:
        palette = SPRITE_COLORS[theme] if art == "sprite" else None
        path = REPO / "assets" / f"card{suffix}-{theme}.svg"
        path.write_text(build(theme, frames, sections, animate, palette))
        print(f"wrote {path.relative_to(REPO)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
