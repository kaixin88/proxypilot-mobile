#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯标准库生成图标（不装 Pillow 也能跑）：圆角渐变方块 + P 字形。
同时产出 PWA 图标与 Android 各密度 launcher 图标。"""

import os
import struct
import zlib

# 5x7 点阵字母 P
GLYPH = [
    "####.",
    "#...#",
    "#...#",
    "####.",
    "#....",
    "#....",
    "#....",
]


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def render(size, radius_ratio=0.22, glyph_ratio=0.46):
    top = (0x3B, 0x7E, 0xF7)
    bot = (0x2F, 0x6D, 0xF6)
    px = [[(0, 0, 0, 0) for _ in range(size)] for _ in range(size)]
    radius = size * radius_ratio

    for y in range(size):
        for x in range(size):
            # 圆角矩形覆盖判定
            cx = min(max(x + 0.5, radius), size - radius)
            cy = min(max(y + 0.5, radius), size - radius)
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            if dx * dx + dy * dy > radius * radius:
                continue
            c = lerp(top, bot, y / max(size - 1, 1))
            px[y][x] = (c[0], c[1], c[2], 255)

    # P 字形
    gw, gh = len(GLYPH[0]), len(GLYPH)
    cell = int(size * glyph_ratio / gh)
    w, h = cell * gw, cell * gh
    ox, oy = (size - w) // 2, (size - h) // 2
    for gy in range(gh):
        for gx in range(gw):
            if GLYPH[gy][gx] != "#":
                continue
            for yy in range(cell):
                for xx in range(cell):
                    x, y = ox + gx * cell + xx, oy + gy * cell + yy
                    if 0 <= x < size and 0 <= y < size:
                        px[y][x] = (255, 255, 255, 255)
    return px


def write_png(path, px):
    size = len(px)
    raw = b""
    for row in px:
        raw += b"\x00" + b"".join(bytes(p) for p in row)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    print("  %-46s %6d B" % (path, len(png)))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print("== 生成图标 ==")
    for size in (192, 512):
        write_png(os.path.join(root, "app", "icon-%d.png" % size), render(size))
    # Android 各密度（方形不透明，符合 launcher 规范）
    for size, dpi in ((48, "mdpi"), (72, "hdpi"), (96, "xhdpi"),
                      (144, "xxhdpi"), (192, "xxxhdpi")):
        write_png(os.path.join(root, "android", "app", "src", "main", "res",
                               "mipmap-" + dpi, "ic_launcher.png"),
                  render(size, radius_ratio=1.0 if size <= 48 else 0.22))
    write_png(os.path.join(root, "android", "app", "src", "main", "res",
                           "drawable", "logo.png"), render(512))


if __name__ == "__main__":
    main()
