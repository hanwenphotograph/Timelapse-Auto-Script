"""Webhook notifications compatible with the original YAML templates."""

from __future__ import annotations

import base64
import hashlib
import shutil
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image


class WebhookClient:
    def __init__(self, config: dict, log: Callable[[str], None]):
        self.config = config
        self.log = log

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled"))

    def _render(
        self, template: str, content: str, image_base64: str = "", image_md5: str = ""
    ) -> str:
        values = {
            "__CONTENT__": content,
            "__TIME__": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "__IMGBASE64__": image_base64,
            "__IMGMD5__": image_md5,
        }
        for token, value in values.items():
            template = template.replace(token, value)
        return template

    def _send(self, event: str, body: str) -> None:
        request = urllib.request.Request(
            str(self.config["url"]),
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read(1)
            self.log(f"webhook 推送成功: {event}")
        except (OSError, urllib.error.URLError) as exc:
            self.log(f"webhook 推送失败: {event}: {exc}")

    def notify(self, event: str, content: str) -> None:
        if not self.enabled:
            return
        self._send(event, self._render(str(self.config["body"]), content))

    def notify_image(self, event: str, content: str, work_dir: Path) -> None:
        if not self.enabled or not self.config.get("push_image"):
            return
        try:
            image_path = self._prepare_image(work_dir)
            image_bytes = image_path.read_bytes()
        except (OSError, ValueError) as exc:
            self.log(f"webhook 图片准备失败: {exc}")
            return
        encoded = base64.b64encode(image_bytes).decode("ascii")
        digest = hashlib.md5(image_bytes).hexdigest()  # noqa: S324 - receiver protocol requires MD5
        template = str(self.config["image_body"])
        self._send(event, self._render(template, content, encoded, digest))

    def _prepare_image(self, work_dir: Path) -> Path:
        hdr_dir = work_dir / "hdr_enfuse"
        extensions = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff"}
        images = sorted(
            path
            for path in hdr_dir.iterdir()
            if path.is_file() and path.suffix.lower() in extensions
        )
        if not images:
            raise ValueError(f"{hdr_dir} 中没有可用图片")
        source = images[(len(images) - 1) // 2]
        post_dir = work_dir / "post_img"
        post_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, post_dir / source.name)
        output = post_dir / "compressed.jpg"
        limit = 2 * 1024 * 1024
        with Image.open(source) as opened:
            image = opened.convert("RGB")
            original_size = image.size
            for scale in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
                width = max(2, int(original_size[0] * scale) // 2 * 2)
                height = max(2, int(original_size[1] * scale) // 2 * 2)
                candidate = (
                    image
                    if scale == 1.0
                    else image.resize((width, height), Image.Resampling.LANCZOS)
                )
                for quality in (92, 84, 76, 68, 60, 50, 40, 30):
                    candidate.save(output, "JPEG", quality=quality, optimize=True)
                    if output.stat().st_size <= limit:
                        return output
        raise ValueError("压缩图片后仍超过 2MB")
