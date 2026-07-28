"""Generate the in-memory image used by webhook delivery tests."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw


def build_test_image() -> bytes:
    image = Image.new("RGB", (640, 360), "#F4F7FB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 640, 72), fill="#2563EB")
    draw.text((32, 27), "Timelapse Manager", fill="#FFFFFF")
    draw.text((32, 132), "Webhook image test", fill="#172033")
    draw.text(
        (32, 176),
        datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        fill="#5D6B82",
    )
    output = BytesIO()
    image.save(output, "JPEG", quality=88, optimize=True)
    return output.getvalue()
