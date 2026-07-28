"""Webhook notifications using configurable JSON templates."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image

from timelapse_manager.errors import WebhookError
from timelapse_manager.webhook_test_image import build_test_image


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
            escaped = json.dumps(value, ensure_ascii=False)[1:-1]
            template = template.replace(token, escaped)
        return template

    def _deliver(self, body: str) -> str:
        url = self.config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise WebhookError("webhook URL 不能为空")
        self._validate_json_body("body", body)
        try:
            request = urllib.request.Request(
                url,
                data=body.encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read()
        except (OSError, ValueError) as exc:
            raise WebhookError(f"网络请求失败: {exc}") from exc
        return self._parse_response(response_body)

    @staticmethod
    def _validate_json_body(name: str, body: str) -> None:
        try:
            json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebhookError(f"webhook {name} 不是有效 JSON: {exc.msg}") from exc

    @staticmethod
    def _parse_response(response_body: bytes) -> str:
        if not response_body:
            return "HTTP 请求成功"
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "HTTP 请求成功"
        if not isinstance(payload, dict) or "errcode" not in payload:
            return "HTTP 请求成功"
        errcode = payload["errcode"]
        message = str(payload.get("errmsg") or "未知错误")
        if errcode not in (0, "0"):
            raise WebhookError(f"企业微信返回错误 {errcode}: {message}")
        return message

    def _send(self, event: str, body: str) -> None:
        try:
            self._deliver(body)
        except WebhookError as exc:
            self.log(f"webhook 推送失败: {event}: {exc}")
        else:
            self.log(f"webhook 推送成功: {event}")

    def test_push(self, content: str = "Timelapse Manager 测试推送") -> str:
        text_template = str(self.config.get("body", ""))
        image_template = str(self.config.get("image_body", ""))
        if "__CONTENT__" not in text_template:
            raise WebhookError("webhook body 必须包含 __CONTENT__")
        for token in ("__IMGBASE64__", "__IMGMD5__"):
            if token not in image_template:
                raise WebhookError(f"webhook image_body 必须包含 {token}")

        image_bytes = build_test_image()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        digest = hashlib.md5(image_bytes).hexdigest()  # noqa: S324 - receiver protocol requires MD5
        text_body = self._render(text_template, content)
        image_body = self._render(image_template, "Webhook 测试图片", encoded, digest)
        self._validate_json_body("body", text_body)
        self._validate_json_body("image_body", image_body)

        text_result = self._deliver(text_body)
        image_result = self._deliver(image_body)
        self.log("webhook 文本与图片测试推送成功")
        return f"文本：{text_result}；图片：{image_result}"

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

    def notify_image_path(
        self,
        event: str,
        content: str,
        source: Path,
        work_dir: Path,
    ) -> None:
        if not self.enabled or not self.config.get("push_image"):
            return
        try:
            image_path = self._compress_image(source, work_dir)
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
        return self._compress_image(source, work_dir)

    def _compress_image(self, source: Path, work_dir: Path) -> Path:
        if not source.is_file():
            raise ValueError(f"图片不存在: {source}")
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
