#!/usr/bin/env python3
"""
Generate Prop Manager app icons as PNG files using only Python stdlib.
Design: Dark navy background, a stylized 'P' diamond shape in electric blue,
        BLE signal arcs radiating from the center-right, subtle star spark.
"""

import struct
import zlib
import math
import os

SIZE = 1024
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Colour palette ──────────────────────────────────────────────────────────
BG       = (15,  17,  23,  255)   # #0f1117 — app background
BLUE1    = (66,  153, 225, 255)   # #4299e1 — primary blue
BLUE2    = (49,  130, 206, 255)   # #3182ce — deeper blue
GLOW     = (99,  179, 237, 200)   # #63b3ed — glow / arcs
WHITE    = (255, 255, 255, 255)
ACCENT   = (237, 137, 54,  255)   # amber spark


# ── Raw PNG writer ──────────────────────────────────────────────────────────

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    c = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', c)


def write_png(path: str, pixels: list, width: int, height: int) -> None:
    """pixels: flat list of (R,G,B,A) tuples, row-major."""
    raw_rows = b''
    for y in range(height):
        row = b'\x00'  # filter type None
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            row += struct.pack('BBBB', r, g, b, a)
        raw_rows += row

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw_rows, 9)

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(_png_chunk(b'IHDR', ihdr))
        f.write(_png_chunk(b'IDAT', idat))
        f.write(_png_chunk(b'IEND', b''))


# ── Drawing helpers ─────────────────────────────────────────────────────────

def lerp(a, b, t):
    return a + (b - a) * t


def blend(dst, src):
    """Alpha-composite src over dst (both RGBA tuples 0-255)."""
    sa = src[3] / 255.0
    da = dst[3] / 255.0
    out_a = sa + da * (1 - sa)
    if out_a < 1e-6:
        return (0, 0, 0, 0)
    r = int((src[0] * sa + dst[0] * da * (1 - sa)) / out_a)
    g = int((src[1] * sa + dst[1] * da * (1 - sa)) / out_a)
    b = int((src[2] * sa + dst[2] * da * (1 - sa)) / out_a)
    a = int(out_a * 255)
    return (
        min(255, r), min(255, g), min(255, b), min(255, a)
    )


def fill_circle(pixels, w, cx, cy, r, colour, aa=True):
    """Draw a filled anti-aliased circle."""
    for y in range(max(0, int(cy - r) - 1), min(w, int(cy + r) + 2)):
        for x in range(max(0, int(cx - r) - 1), min(w, int(cx + r) + 2)):
            d = math.hypot(x - cx, y - cy)
            if d < r - 0.5:
                alpha = colour[3]
            elif d < r + 0.5:
                alpha = int(colour[3] * (r + 0.5 - d))
            else:
                continue
            c = (colour[0], colour[1], colour[2], alpha)
            pixels[y * w + x] = blend(pixels[y * w + x], c)


def fill_rect(pixels, w, x0, y0, x1, y1, colour):
    for y in range(max(0, y0), min(w, y1)):
        for x in range(max(0, x0), min(w, x1)):
            pixels[y * w + x] = blend(pixels[y * w + x], colour)


def draw_arc(pixels, w, cx, cy, r, thickness, start_deg, end_deg, colour, aa=True):
    """Draw an arc by tracing sample points along the ring."""
    steps = max(200, int(abs(end_deg - start_deg) * r * math.pi / 180))
    for i in range(steps + 1):
        t = i / steps
        angle = math.radians(lerp(start_deg, end_deg, t))
        for dr in range(-int(thickness / 2) - 1, int(thickness / 2) + 2):
            rr = r + dr
            px = cx + rr * math.cos(angle)
            py = cy + rr * math.sin(angle)
            ix, iy = int(px), int(py)
            if 0 <= ix < w and 0 <= iy < w:
                # Sub-pixel alpha
                frac = abs(dr) / (thickness / 2 + 0.5)
                alpha = int(colour[3] * max(0, 1 - frac ** 2))
                c = (colour[0], colour[1], colour[2], alpha)
                pixels[iy * w + ix] = blend(pixels[iy * w + ix], c)


def draw_line(pixels, w, x0, y0, x1, y1, thickness, colour):
    """Bresenham-ish thick line with AA."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1
    steps = int(length * 2)
    for i in range(steps + 1):
        t = i / steps
        cx = x0 + dx * t
        cy = y0 + dy * t
        fill_circle(pixels, w, cx, cy, thickness / 2, colour)


# ── Main icon design ─────────────────────────────────────────────────────────
# Concept: large stylised Bluetooth diamond (B-shape) in blue on the left half,
# three concentric signal arcs fanning right, amber spark dot in top-right.

def render_icon(size: int) -> list:
    s = size
    pixels = [BG] * (s * s)

    cx = s * 0.42   # slightly left-of-centre to leave room for arcs
    cy = s * 0.50

    # ── Solid background card ────────────────────────────────────────────────
    # Fill the entire canvas with a slightly lighter dark card colour.
    # The launcher / OS handles the rounded-square clipping mask.
    card_col = (22, 26, 38, 255)
    fill_rect(pixels, s, 0, 0, s, s, card_col)

    # ── Bluetooth symbol (classic diamond + B-shape) ─────────────────────────
    # Vertical spine
    spine_top    = cy - s * 0.30
    spine_bottom = cy + s * 0.30
    spine_cx     = cx - s * 0.03
    thick = s * 0.055

    draw_line(pixels, s,
              int(spine_cx), int(spine_top),
              int(spine_cx), int(spine_bottom),
              thick, BLUE1)

    # Upper-right arm → tip → return (forms top half of B)
    tip_top = (spine_cx + s * 0.18, cy - s * 0.15)
    draw_line(pixels, s, int(spine_cx), int(spine_top),  int(tip_top[0]), int(tip_top[1]), thick, BLUE1)
    draw_line(pixels, s, int(tip_top[0]), int(tip_top[1]), int(spine_cx), int(cy),           thick, BLUE1)

    # Lower-right arm (forms bottom half of B)
    tip_bot = (spine_cx + s * 0.18, cy + s * 0.15)
    draw_line(pixels, s, int(spine_cx), int(cy),          int(tip_bot[0]), int(tip_bot[1]), thick, BLUE2)
    draw_line(pixels, s, int(tip_bot[0]), int(tip_bot[1]), int(spine_cx), int(spine_bottom), thick, BLUE2)

    # ── Signal / WiFi arcs (right side) ─────────────────────────────────────
    arc_cx  = cx + s * 0.08   # arc origin slightly right of symbol
    arc_cy  = cy
    arc_start = -50
    arc_end   = 50
    arc_thicknesses = [s * 0.032, s * 0.030, s * 0.028]
    arc_radii = [s * 0.26, s * 0.38, s * 0.50]
    arc_alphas = [240, 180, 110]

    for i, (r2, t2, alpha2) in enumerate(zip(arc_radii, arc_thicknesses, arc_alphas)):
        c = (GLOW[0], GLOW[1], GLOW[2], alpha2)
        draw_arc(pixels, s, arc_cx, arc_cy, r2, t2, arc_start, arc_end, c)

    # Centre dot for arcs
    fill_circle(pixels, s, arc_cx, arc_cy, thick * 0.75, BLUE1)

    # ── Amber spark (top-right area) ─────────────────────────────────────────
    spark_cx = cx + s * 0.24
    spark_cy = cy - s * 0.30
    fill_circle(pixels, s, spark_cx, spark_cy, s * 0.028, ACCENT)
    fill_circle(pixels, s, spark_cx, spark_cy, s * 0.016, WHITE)

    return pixels


def render_foreground(size: int) -> list:
    """Android adaptive icon foreground — same design, transparent BG."""
    s = size
    pixels = [(0, 0, 0, 0)] * (s * s)

    cx = s * 0.42
    cy = s * 0.50
    thick = s * 0.055
    spine_cx = cx - s * 0.03
    spine_top = cy - s * 0.30
    spine_bottom = cy + s * 0.30

    draw_line(pixels, s, int(spine_cx), int(spine_top), int(spine_cx), int(spine_bottom), thick, BLUE1)
    tip_top = (spine_cx + s * 0.18, cy - s * 0.15)
    draw_line(pixels, s, int(spine_cx), int(spine_top), int(tip_top[0]), int(tip_top[1]), thick, BLUE1)
    draw_line(pixels, s, int(tip_top[0]), int(tip_top[1]), int(spine_cx), int(cy), thick, BLUE1)
    tip_bot = (spine_cx + s * 0.18, cy + s * 0.15)
    draw_line(pixels, s, int(spine_cx), int(cy), int(tip_bot[0]), int(tip_bot[1]), thick, BLUE2)
    draw_line(pixels, s, int(tip_bot[0]), int(tip_bot[1]), int(spine_cx), int(spine_bottom), thick, BLUE2)

    arc_cx = cx + s * 0.08
    arc_cy = cy
    for r2, alpha2 in zip([s * 0.26, s * 0.38, s * 0.50], [240, 180, 110]):
        c = (GLOW[0], GLOW[1], GLOW[2], alpha2)
        draw_arc(pixels, s, arc_cx, arc_cy, r2, s * 0.030, -50, 50, c)
    fill_circle(pixels, s, arc_cx, arc_cy, thick * 0.75, BLUE1)

    spark_cx = cx + s * 0.24
    spark_cy = cy - s * s * 0.00030  # keep proportional
    spark_cy = cy - s * 0.30
    fill_circle(pixels, s, spark_cx, spark_cy, s * 0.028, ACCENT)
    fill_circle(pixels, s, spark_cx, spark_cy, s * 0.016, WHITE)

    return pixels


def render_background(size: int) -> list:
    """Android adaptive icon background — solid dark card."""
    s = size
    pixels = [(22, 26, 38, 255)] * (s * s)
    return pixels


def render_monochrome(size: int) -> list:
    """Android monochrome — white-on-transparent Bluetooth + arcs."""
    s = size
    pixels = [(0, 0, 0, 0)] * (s * s)
    WHITE_F = (255, 255, 255, 255)
    GREY    = (200, 200, 200, 180)

    cx = s * 0.42
    cy = s * 0.50
    thick = s * 0.055
    spine_cx = cx - s * 0.03
    spine_top = cy - s * 0.30
    spine_bottom = cy + s * 0.30

    draw_line(pixels, s, int(spine_cx), int(spine_top), int(spine_cx), int(spine_bottom), thick, WHITE_F)
    tip_top = (spine_cx + s * 0.18, cy - s * 0.15)
    draw_line(pixels, s, int(spine_cx), int(spine_top), int(tip_top[0]), int(tip_top[1]), thick, WHITE_F)
    draw_line(pixels, s, int(tip_top[0]), int(tip_top[1]), int(spine_cx), int(cy), thick, WHITE_F)
    tip_bot = (spine_cx + s * 0.18, cy + s * 0.15)
    draw_line(pixels, s, int(spine_cx), int(cy), int(tip_bot[0]), int(tip_bot[1]), thick, WHITE_F)
    draw_line(pixels, s, int(tip_bot[0]), int(tip_bot[1]), int(spine_cx), int(spine_bottom), thick, WHITE_F)

    arc_cx = cx + s * 0.08
    arc_cy = cy
    for r2, alpha2 in zip([s * 0.26, s * 0.38, s * 0.50], [240, 180, 110]):
        c = (255, 255, 255, alpha2)
        draw_arc(pixels, s, arc_cx, arc_cy, r2, s * 0.030, -50, 50, c)
    fill_circle(pixels, s, arc_cx, arc_cy, thick * 0.75, WHITE_F)

    return pixels


if __name__ == '__main__':
    print("Generating icons…")

    # Main icon (1024×1024)
    write_png(os.path.join(OUT_DIR, 'icon.png'), render_icon(1024), 1024, 1024)
    print("  icon.png")

    # Splash icon (smaller, white BT logo on dark)
    write_png(os.path.join(OUT_DIR, 'splash-icon.png'), render_icon(512), 512, 512)
    print("  splash-icon.png")

    # Adaptive foreground (1024)
    write_png(os.path.join(OUT_DIR, 'android-icon-foreground.png'), render_foreground(1024), 1024, 1024)
    print("  android-icon-foreground.png")

    # Adaptive background (1024)
    write_png(os.path.join(OUT_DIR, 'android-icon-background.png'), render_background(1024), 1024, 1024)
    print("  android-icon-background.png")

    # Monochrome (1024)
    write_png(os.path.join(OUT_DIR, 'android-icon-monochrome.png'), render_monochrome(1024), 1024, 1024)
    print("  android-icon-monochrome.png")

    # Favicon (64)
    write_png(os.path.join(OUT_DIR, 'favicon.png'), render_icon(64), 64, 64)
    print("  favicon.png")

    print("Done.")
