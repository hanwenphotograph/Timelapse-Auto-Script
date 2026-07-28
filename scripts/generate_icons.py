#!/usr/bin/env python3
"""Generate application icons from the sidebar TL brand mark."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "timelapse_manager" / "assets"
ACCENT = "#3977F6"
ICON_SIZE = 1024
ICON_MARGIN = 104


def _font_path() -> Path:
    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("未找到可用于生成应用图标的粗体字体")


def build_icon() -> Image.Image:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (
            ICON_MARGIN,
            ICON_MARGIN,
            ICON_SIZE - ICON_MARGIN,
            ICON_SIZE - ICON_MARGIN,
        ),
        radius=204,
        fill=ACCENT,
    )
    font = ImageFont.truetype(str(_font_path()), 374)
    draw.text(
        (ICON_SIZE // 2, ICON_SIZE // 2 + 7),
        "TL",
        fill="#FFFFFF",
        font=font,
        anchor="mm",
    )
    return image


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    icon = build_icon()
    icon.save(ASSET_DIR / "timelapse-manager.png", optimize=True)
    icon.save(
        ASSET_DIR / "timelapse-manager.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    icon.save(ASSET_DIR / "timelapse-manager.icns")
    print(ASSET_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
