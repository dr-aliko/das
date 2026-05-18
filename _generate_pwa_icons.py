"""
One-off script — generates PWA icon PNGs using only Python stdlib.
Run once, then delete (or keep as a dev tool for regeneration).
Output: static/img/icons/{icon-192,icon-512,icon-maskable-512,apple-touch-icon}.png
"""
import struct
import zlib
import math
import os

ICON_DIR = os.path.join(os.path.dirname(__file__), "static", "img", "icons")

# Brand colours  (indigo-600 background, white foreground)
BG  = (79, 70, 229)   # #4f46e5
FG  = (255, 255, 255)

def make_png(width, height, get_pixel):
    """Return raw PNG bytes.  get_pixel(x, y) -> (r, g, b)."""
    def chunk(tag, data):
        crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + tag + data + crc

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    rows = []
    for y in range(height):
        row = bytearray([0])           # filter byte: None
        for x in range(width):
            row += bytearray(get_pixel(x, y))
        rows.append(bytes(row))

    idat = chunk(b"IDAT", zlib.compress(b"".join(rows)))
    iend = chunk(b"IEND", b"")

    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def circle_icon(size, bg, fg, pad_ratio=0.18):
    """
    Solid bg square with a centered white circle whose radius fills ~60% of
    the canvas (after the given safe-zone padding).
    """
    cx = cy = size / 2
    # Inner circle radius — leaves pad_ratio margin on each side
    r  = size * (0.5 - pad_ratio)
    # Inner "D" letter approximated by a filled circle (clean, minimal)
    # Paint: bg everywhere; FG inside circle
    r2 = r * r

    def pixel(x, y):
        dx, dy = x - cx + 0.5, y - cy + 0.5
        return fg if dx * dx + dy * dy <= r2 else bg

    return pixel


def letter_icon(size, bg, fg, pad_ratio=0.18):
    """
    Solid bg square with a pixelated 'D' glyph centered in the canvas.
    The 'D' is drawn as a filled semicircle on the right + vertical bar.
    """
    cx = cy = size / 2
    # Overall glyph box — stays inside safe zone
    margin  = size * pad_ratio
    gw = gh = size - 2 * margin        # glyph width/height

    bar_w   = gw * 0.22               # left vertical bar width
    arc_cx  = margin + bar_w           # center-x of the arc circle
    arc_r   = gh / 2                  # arc radius (half glyph height)
    arc_cy  = cy                       # arc center-y

    arc_r2  = arc_r * arc_r

    def pixel(x, y):
        px, py = x + 0.5, y + 0.5
        # Left vertical bar
        in_bar = (margin <= px <= margin + bar_w) and (margin <= py <= margin + gh)
        # Right semicircle (only right half of the circle + inside safe zone)
        dx, dy = px - arc_cx, py - arc_cy
        in_arc = (dx * dx + dy * dy <= arc_r2) and (px >= arc_cx)
        # Hollow the middle — remove a slightly smaller arc from the inside
        inner_r  = arc_r * 0.58
        inner_r2 = inner_r * inner_r
        in_hole  = (dx * dx + dy * dy <= inner_r2) and (px >= arc_cx + bar_w * 0.5)
        return fg if (in_bar or in_arc) and not in_hole else bg

    return pixel


ICONS = [
    ("icon-192.png",         192, False),
    ("icon-512.png",         512, False),
    ("icon-maskable-512.png", 512, True),   # maskable needs more padding
    ("apple-touch-icon.png", 180, False),
]

for filename, size, maskable in ICONS:
    pad = 0.20 if maskable else 0.14       # maskable safe zone is larger
    pixel_fn = letter_icon(size, BG, FG, pad_ratio=pad)
    data = make_png(size, size, pixel_fn)
    path = os.path.join(ICON_DIR, filename)
    with open(path, "wb") as f:
        f.write(data)
    print(f"  wrote {path}  ({size}x{size})")

print("Done.")
