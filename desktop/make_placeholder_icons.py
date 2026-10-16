#!/usr/bin/env python3
"""Draw simple stand-in icons for artwork that isn't in the public repo.

The Beebo screen uses about 70 icon images (menu buttons, tuner graphics,
module pictures) that ship on the pedal but were never committed to
polyeffects/digit_ui. Without them the buttons still work but are blank.

This draws plain white line icons for every missing file the QML refers to
by name. Real artwork always wins: anything already present (for example
copied from /home/debian/UI/icons on your pedal) is left alone.

    python3 desktop/make_placeholder_icons.py [UI folder]
"""
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

UI = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".."))
FONT = os.path.join(UI, "qml", "fonts", "BarlowSemiCondensed-SemiBold.ttf")
S = 120             # drawn at 2x the 60 px the screen uses
W = (255, 255, 255, 255)
LW = 8


def canvas(w=S, h=S):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def text_icon(label, w=S, h=S):
    img, d = canvas(w, h)
    size = int(h * 0.42)
    f = font(size)
    while d.textlength(label, font=f) > w * 0.92 and size > 10:
        size -= 2
        f = font(size)
    d.text((w / 2, h / 2), label, font=f, fill=W, anchor="mm")
    return img


def star(d, filled):
    pts = []
    for i in range(10):
        r = 48 if i % 2 == 0 else 20
        a = math.pi / 2 + i * math.pi / 5
        pts.append((60 + r * math.cos(a), 64 - r * math.sin(a)))
    if filled:
        d.polygon(pts, fill=W)
    else:
        d.line(pts + [pts[0]], fill=W, width=6, joint="curve")


def arrow(d, direction):
    if direction == "left":
        d.line([(95, 60), (25, 60)], fill=W, width=LW)
        d.line([(55, 30), (25, 60), (55, 90)], fill=W, width=LW, joint="curve")
    elif direction == "up":
        d.line([(60, 95), (60, 25)], fill=W, width=LW)
        d.line([(30, 55), (60, 25), (90, 55)], fill=W, width=LW, joint="curve")
    else:
        d.line([(60, 25), (60, 95)], fill=W, width=LW)
        d.line([(30, 65), (60, 95), (90, 65)], fill=W, width=LW, joint="curve")


def trash(d):
    d.line([(25, 32), (95, 32)], fill=W, width=LW)
    d.line([(48, 32), (50, 20), (70, 20), (72, 32)], fill=W, width=6)
    d.line([(33, 32), (40, 100), (80, 100), (87, 32)], fill=W, width=LW, joint="curve")
    for x in (50, 60, 70):
        d.line([(x, 45), (x, 88)], fill=W, width=5)


def gear(d):
    for i in range(8):
        a = i * math.pi / 4
        d.line([(60 + 30 * math.cos(a), 60 + 30 * math.sin(a)),
                (60 + 50 * math.cos(a), 60 + 50 * math.sin(a))], fill=W, width=14)
    d.ellipse([22, 22, 98, 98], outline=W, width=LW)
    d.ellipse([46, 46, 74, 74], outline=W, width=6)


def draw(name):
    """Return an image for this icon file name, or None for a text label."""
    n = name.lower()
    img, d = canvas()
    if n in ("add",):
        d.line([(60, 22), (60, 98)], fill=W, width=LW)
        d.line([(22, 60), (98, 60)], fill=W, width=LW)
    elif n in ("delete", "bin"):
        trash(d)
    elif n == "duplicate":
        d.rectangle([22, 36, 74, 98], outline=W, width=LW)
        d.line([(42, 22), (98, 22), (98, 80)], fill=W, width=LW)
    elif n == "disconnect":
        d.arc([10, 40, 60, 80], 90, 270, fill=W, width=LW)
        d.arc([60, 40, 110, 80], 270, 90, fill=W, width=LW)
        d.line([(55, 25), (65, 95)], fill=W, width=6)
    elif n == "settings":
        gear(d)
    elif n == "back":
        arrow(d, "left")
    elif n == "more":
        for x in (30, 60, 90):
            d.ellipse([x - 9, 51, x + 9, 69], fill=W)
    elif n == "patch":
        d.ellipse([12, 72, 36, 96], outline=W, width=6)
        d.ellipse([84, 24, 108, 48], outline=W, width=6)
        d.arc([24, 10, 110, 150], 200, 300, fill=W, width=6)
    elif n == "spotlight":
        d.polygon([(60, 15), (30, 100), (90, 100)], outline=W, width=6)
        d.ellipse([45, 8, 75, 30], fill=W)
    elif n in ("up", "down"):
        arrow(d, n)
    elif n == "fav":
        star(d, True)
    elif n == "not_fav":
        star(d, False)
    elif n == "on":
        d.ellipse([20, 20, 100, 100], fill=W)
    elif n == "off":
        d.ellipse([20, 20, 100, 100], outline=W, width=LW)
    elif n == "move":
        d.line([(60, 15), (60, 105)], fill=W, width=6)
        d.line([(15, 60), (105, 60)], fill=W, width=6)
        for p in ([(48, 28), (60, 15), (72, 28)], [(48, 92), (60, 105), (72, 92)],
                  [(28, 48), (15, 60), (28, 72)], [(92, 48), (105, 60), (92, 72)]):
            d.line(p, fill=W, width=6)
    elif n == "shapes":
        d.polygon([(30, 95), (55, 45), (80, 95)], outline=W, width=6)
        d.ellipse([60, 20, 100, 60], outline=W, width=6)
    elif n in ("midi_active", "midi_inactive", "midi"):
        d.ellipse([15, 15, 105, 105], outline=W, width=LW)
        for a in (200, 240, 270, 300, 340):
            r = math.radians(a)
            x, y = 60 + 28 * math.cos(r), 62 + 28 * math.sin(r)
            if n == "midi_active":
                d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=W)
            else:
                d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=W, width=3)
    elif n in ("play icon",):
        d.polygon([(35, 20), (35, 100), (100, 60)], fill=W)
    elif n in ("reverse-play-icon",):
        d.polygon([(85, 20), (85, 100), (20, 60)], fill=W)
    elif n == "undo":
        d.arc([25, 30, 95, 100], 180, 90, fill=W, width=LW)
        d.polygon([(10, 60), (40, 60), (25, 35)], fill=W)
    elif n == "tick":
        d.line([(20, 62), (48, 90), (100, 30)], fill=W, width=LW, joint="curve")
    elif n == "cross":
        d.line([(25, 25), (95, 95)], fill=W, width=LW)
        d.line([(95, 25), (25, 95)], fill=W, width=LW)
    else:
        return None
    return img


SIZES = {
    # images shown at a fixed size rather than as a 60 px icon
    "icons/digit/Hector.png": ("HECTOR", 212, 136),
    "icons/digit/hector_background.png": (None, 1280, 720),
    "icons/digit/tuner/tuner_rainbow_lines.png": (None, 1000, 300),
    "icons/digit/tuner/indicator_line.png": ("|", 20, 300),
}


def make(rel):
    path = os.path.join(UI, rel)
    stem = os.path.splitext(os.path.basename(rel))[0]
    if rel in SIZES:
        label, w, h = SIZES[rel]
        img = text_icon(label, w, h) if label else Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        img = draw(stem) or text_icon(stem.replace("_", " ").replace("-", " ").upper()[:10])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def referenced_icons():
    refs = set()
    for root, _, files in os.walk(os.path.join(UI, "qml")):
        for f in files:
            if f.endswith((".qml", ".js")):
                with open(os.path.join(root, f), encoding="utf-8", errors="ignore") as fh:
                    for m in re.finditer(r'"(?:\.\./)?(icons/[^"+]+\.png)"', fh.read()):
                        refs.add(m.group(1))
    return sorted(refs)


def main():
    made = 0
    for rel in referenced_icons():
        if not os.path.exists(os.path.join(UI, rel)):
            make(rel)
            made += 1
    print("placeholder icons drawn: %d" % made)


if __name__ == "__main__":
    main()
