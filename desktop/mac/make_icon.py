#!/usr/bin/env python3
"""Make Beebo.icns (the app icon) from the Beebo logo in icons/digit."""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = sys.argv[1]
logo = Image.open(os.path.join(ROOT, "icons", "digit", "Beebo.png")).convert("RGBA")
size = 1024
icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
# rounded square in the Beebo pink, logo centred on it
from PIL import ImageDraw  # noqa: E402
d = ImageDraw.Draw(icon)
d.rounded_rectangle([64, 64, size - 64, size - 64], radius=180, fill=(255, 162, 222, 255))
w = int(size * 0.72)
h = int(logo.height * w / logo.width)
logo = logo.resize((w, h), Image.LANCZOS)
icon.alpha_composite(logo, ((size - w) // 2, (size - h) // 2))
icon.save(out, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
print("icon:", out)
