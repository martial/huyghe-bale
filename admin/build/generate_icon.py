"""Generate a 1024x1024 icon for PIERRE HUYGHE BALE Mac app.

Minimal gallery-aesthetic: dark background with two flowing curves
representing the A/B PWM channels.
"""

import math
import sys

from PIL import Image, ImageDraw, ImageFilter


def generate_icon(output_path: str) -> None:
    SIZE = 1024
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    cx, cy = SIZE // 2, SIZE // 2

    # --- Rounded rect mask (macOS squircle-like) ---
    mask = Image.new("L", (SIZE, SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    r = 220
    mask_draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=r, fill=255)

    # --- Radial gradient background (concentric circles, fast) ---
    bg = Image.new("RGBA", (SIZE, SIZE), (14, 14, 14, 255))
    bg_draw = ImageDraw.Draw(bg)
    max_r = int(SIZE * 0.7)
    for radius in range(max_r, 0, -2):
        t = 1.0 - (radius / max_r)
        v = int(14 + t * 22)  # 14 at edge -> 36 at center
        bg_draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=(v, v, v, 255),
        )
    bg.putalpha(mask)
    img = Image.alpha_composite(img, bg)

    # --- Curve helpers ---
    def make_curve_points(y_func, margin=80):
        points = []
        for px in range(margin, SIZE - margin):
            t = (px - margin) / (SIZE - 2 * margin)
            points.append((px, y_func(t)))
        return points

    def draw_curve(image, points, color, width=5, glow_color=None):
        if len(points) < 2:
            return image
        if glow_color:
            glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            glow_draw.line(points, fill=glow_color, width=width + 20, joint="curve")
            glow = glow.filter(ImageFilter.GaussianBlur(radius=16))
            image = Image.alpha_composite(image, glow)
        line = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        line_draw = ImageDraw.Draw(line)
        line_draw.line(points, fill=color, width=width, joint="curve")
        line = line.filter(ImageFilter.GaussianBlur(radius=0.7))
        image = Image.alpha_composite(image, line)
        return image

    # Curve A — cool blue-white, flowing sine
    def curve_a(t):
        base = SIZE * 0.38
        amp = SIZE * 0.13
        return base + amp * math.sin(t * math.pi * 2.5 + 0.3) * (
            0.6 + 0.4 * math.sin(t * math.pi * 1.2)
        )

    # Curve B — warm amber, phase-shifted
    def curve_b(t):
        base = SIZE * 0.62
        amp = SIZE * 0.11
        return base + amp * math.sin(t * math.pi * 2.8 - 0.8) * (
            0.5 + 0.5 * math.cos(t * math.pi * 0.9)
        )

    pts_a = make_curve_points(curve_a)
    pts_b = make_curve_points(curve_b)

    img = draw_curve(
        img, pts_a, (190, 210, 240, 230), width=5, glow_color=(120, 160, 220, 50)
    )
    img = draw_curve(
        img, pts_b, (230, 175, 90, 230), width=5, glow_color=(200, 140, 50, 45)
    )

    # Apply mask to final composited image
    final = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    final.paste(img, mask=mask)

    final.save(output_path, "PNG")
    print(f"Icon saved: {output_path}")


def generate_ico(png_path: str, ico_path: str) -> None:
    """Convert a PNG icon to a multi-resolution Windows .ico file."""
    img = Image.open(png_path)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=sizes)
    print(f"ICO saved: {ico_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon_1024.png"
    generate_icon(out)

    if "--ico" in sys.argv:
        ico_out = sys.argv[sys.argv.index("--ico") + 1] if sys.argv.index("--ico") + 1 < len(sys.argv) else "app_icon.ico"
        generate_ico(out, ico_out)
