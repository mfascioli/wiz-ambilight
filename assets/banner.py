#!/usr/bin/env python3
"""Generate the HUD-style banners used by the README.

Same visual language as the panel and as github.com/mfascioli/mpv-config:
charcoal gradient, faint grid, amber #FCBE11 glow, corner brackets and
condensed sans type. Everything is drawn deterministically with Pillow and the
bundled Fira Sans Condensed (SIL OFL), so the text is exact and the output is
reproducible.

    python3 assets/banner.py            # writes the banners next to this file
    python3 assets/banner.py --out DIR  # write somewhere else

Requires Pillow and numpy. This is a documentation tool: the player and the
panel never import it, and `assets/banner-fonts/` is never served.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE / "banner-fonts"

AMBER = (252, 190, 17)
AMBER_DIM = (201, 154, 38)
WARM_WHITE = (242, 232, 206)
GREY = (107, 107, 114)
BG_TOP = (11, 11, 12)
BG_BOTTOM = (22, 19, 16)

FONT_FILES = {
    "regular": "FiraSansCondensed-Regular.ttf",
    "semibold": "FiraSansCondensed-SemiBold.ttf",
    "heavy": "FiraSansCondensed-Heavy.ttf",
}


def font(weight, size):
    return ImageFont.truetype(str(FONT_DIR / FONT_FILES[weight]), size)


def vertical_gradient(w, h, top, bottom):
    ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    rows = np.array(top, dtype=np.float32)[None, None, :] * (1 - ramp) + np.array(
        bottom, dtype=np.float32
    )[None, None, :] * ramp
    return Image.fromarray(np.repeat(rows.astype(np.uint8), w, axis=1), "RGB").convert("RGBA")


def add_glow(img, cx, cy, rx, ry, strength):
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    alpha = (np.clip(1.0 - dist, 0.0, 1.0) ** 2 * strength).astype(np.uint8)
    layer = np.zeros((h, w, 4), dtype=np.uint8)
    layer[..., 0:3] = AMBER
    layer[..., 3] = alpha
    return Image.alpha_composite(img, Image.fromarray(layer, "RGBA"))


def add_grid(img, step=64, alpha=9):
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(255, 216, 107, alpha))
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(255, 216, 107, alpha))
    return Image.alpha_composite(img, layer)


def add_frame(img, inset=26, arm=104, width=4):
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([inset, inset, w - inset - 1, h - inset - 1], outline=(252, 190, 17, 40), width=1)
    for x, y, dx, dy in (
        (inset, inset, 1, 1),
        (w - inset - 1, inset, -1, 1),
        (inset, h - inset - 1, 1, -1),
        (w - inset - 1, h - inset - 1, -1, -1),
    ):
        d.line([(x, y), (x + dx * arm, y)], fill=(252, 190, 17, 210), width=width)
        d.line([(x, y), (x, y + dy * arm)], fill=(252, 190, 17, 210), width=width)
    return Image.alpha_composite(img, layer)


def canvas(w, h, glow, inset=26, arm=104):
    img = vertical_gradient(w, h, BG_TOP, BG_BOTTOM)
    img = add_glow(img, *glow)
    img = add_grid(img)
    return add_frame(img, inset=inset, arm=arm)


def text_width(d, text, f, tracking=0):
    if not text:
        return 0
    return sum(d.textlength(c, font=f) for c in text) + tracking * (len(text) - 1)


def draw_tracked(d, xy, text, f, fill, tracking=0):
    x, y = xy
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + tracking


def draw_right(d, x_right, y, text, f, fill, tracking=0):
    draw_tracked(d, (x_right - text_width(d, text, f, tracking), y), text, f, fill, tracking)


def hero(path, version):
    w, h = 1600, 470
    img = canvas(w, h, (520, 235, 640, 250, 24))
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    o = ImageDraw.Draw(ov)

    o.line([(140, 322), (1460, 322)], fill=(252, 190, 17, 60), width=1)

    chips = ("MPV FRAMES", "18 HZ FADE", "UDP 38899", "ZERO DEPS")
    chip_font = font("semibold", 20)
    boxes = []
    x = 140
    for label in chips:
        tw = text_width(o, label, chip_font, 3)
        box = [x, 348, x + tw + 40, 392]
        o.rounded_rectangle(box, radius=5, fill=(252, 190, 17, 14), outline=(252, 190, 17, 85), width=1)
        boxes.append((box, label))
        x = box[2] + 16

    rows = (
        ("CAPTURE", "15 FPS"),
        ("SEND", "18 HZ"),
        ("TRANSPORT", "LOCAL UDP"),
        ("DEPENDENCIES", "NONE"),
    )
    y = 196
    for _label, _value in rows:
        o.line([(1040, y + 40), (1460, y + 40)], fill=(255, 216, 107, 26), width=1)
        y += 48

    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img)

    draw_tracked(d, (140, 64), "DIY AMBILIGHT FOR WIZ", font("semibold", 20), AMBER_DIM, 6)
    d.text((136, 92), "WIZ AMBILIGHT", font=font("heavy", 108), fill=AMBER)
    d.text((144, 232), "Video colour on your walls \u00b7 local UDP \u00b7 no dependencies",
           font=font("regular", 32), fill=WARM_WHITE)
    d.text((144, 276), "Reads the frame mpv already decoded. No capture card, no cloud.",
           font=font("regular", 24), fill=GREY)

    for box, label in boxes:
        draw_tracked(d, (box[0] + 20, box[1] + 11), label, chip_font, AMBER, 3)

    y = 196
    for label, value in rows:
        draw_tracked(d, (1040, y + 2), label, font("semibold", 16), GREY, 4)
        draw_right(d, 1460, y, value, font("semibold", 24), WARM_WHITE, 1)
        y += 48

    d.text((140, 414), "mpv  \u00b7  Python 3.9+  \u00b7  Linux \u00b7 macOS  \u00b7  WiZ on your LAN",
           font=font("regular", 18), fill=GREY)
    draw_right(d, 1460, 44, version, font("regular", 18), GREY)

    img.convert("RGB").save(path, optimize=True)


def strip(path, kicker, title, detail):
    w, h = 1200, 158
    img = canvas(w, h, (360, 79, 400, 126, 16), inset=18, arm=56)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    o = ImageDraw.Draw(ov)
    o.line([(640, 42), (640, 126)], fill=(252, 190, 17, 45), width=1)
    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img)

    draw_tracked(d, (60, 24), kicker, font("semibold", 20), AMBER_DIM, 5)
    d.text((56, 50), title, font=font("heavy", 58), fill=AMBER)
    draw_right(d, 1140, 64, detail, font("semibold", 25), WARM_WHITE, 1)

    img.convert("RGB").save(path, optimize=True)


STRIPS = (
    ("overview.png", "OVERVIEW", "FRAME TO WALL",
     "mpv \u00b7 Lua \u00b7 Python \u00b7 UDP"),
    ("features.png", "FEATURES", "WHAT YOU GET",
     "local \u00b7 multi-bulb \u00b7 panel"),
    ("requirements.png", "REQUIREMENTS", "WHAT YOU NEED",
     "mpv \u00b7 Python 3.9+ \u00b7 WiZ bulbs"),
    ("install.png", "INSTALLATION", "ONE CLONE",
     "start the panel"),
    ("quickstart.png", "QUICK START", "PANEL FIRST",
     "scan \u00b7 pick \u00b7 play"),
    ("panel.png", "WEB PANEL", "LOCAL ONLY",
     "127.0.0.1 \u00b7 token \u00b7 CSP"),
    ("modes.png", "OPERATING MODES", "TWO SOURCES",
     "your file \u00b7 your mpv"),
    ("configuration.png", "CONFIGURATION", "LOOK AND COST",
     "layouts \u00b7 styles \u00b7 sampling"),
    ("design.png", "DESIGN", "AMBER, NOT WHITE",
     "#FCBE11 \u00b7 Merriweather \u00b7 HUD"),
    ("styles.png", "STYLES", "CAPTURE, FADE, SEND",
     "12\u201324 fps \u00b7 0\u2013220 ms \u00b7 15\u201330 Hz"),
    ("layouts.png", "LAYOUTS AND ZONES", "EDGE TO EDGE",
     "sides \u00b7 thirds \u00b7 whole frame"),
    ("attach.png", "ATTACH", "YOUR OWN MPV",
     "install once \u00b7 idles until live"),
    ("control.png", "COMMAND LINE", "TERMINAL, TOO",
     "launch \u00b7 attach \u00b7 set"),
    ("how.png", "HOW IT WORKS", "FRAME TO BULB",
     "sample \u00b7 fade \u00b7 setPilot"),
    ("performance.png", "PERFORMANCE", "FPS IS THE COST",
     "4K: --fps 8"),
    ("troubleshooting.png", "TROUBLESHOOTING", "WHEN IT MISBEHAVES",
     "discovery \u00b7 VLAN \u00b7 video output"),
    ("development.png", "DEVELOPMENT", "NO DEPENDENCIES",
     "unittest \u00b7 py_compile \u00b7 lua"),
    ("roadmap.png", "ROADMAP", "WHAT IS MISSING",
     "Windows \u00b7 transport \u00b7 UI/UX"),
    ("privacy.png", "PRIVACY & SECURITY", "LAN ONLY, BY DESIGN",
     "no cloud \u00b7 no account \u00b7 token"),
    ("credits.png", "CREDITS", "BUILT ON",
     "mpv \u00b7 wiz-hack \u00b7 Merriweather"),
    ("related.png", "RELATED PROJECTS", "ALSO IN MPV",
     "mpv-config"),
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=HERE)
    p.add_argument("--version", default="v1.10.0")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    hero(a.out / "banner.png", a.version)
    for name, kicker, title, detail in STRIPS:
        strip(a.out / name, kicker, title, detail)
    print(f"wrote {a.out / 'banner.png'}")
    for name, _kicker, _title, _detail in STRIPS:
        print(f"wrote {a.out / name}")


if __name__ == "__main__":
    main()
