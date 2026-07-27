from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from timelapse_manager.webhook import WebhookClient


class WebhookImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp.name) / "work"
        self.hdr_dir = self.work_dir / "hdr_enfuse"
        self.hdr_dir.mkdir(parents=True)
        self.config = {
            "enabled": True,
            "url": "https://example.invalid/webhook",
            "body": '{"content":"__CONTENT__"}',
            "push_image": True,
            "image_body": (
                '{"content":"__CONTENT__","image":"__IMGBASE64__","md5":"__IMGMD5__"}'
            ),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_notify_image_path_uses_the_requested_photo(self) -> None:
        first = self.hdr_dir / "first.jpg"
        highest = self.hdr_dir / "highest.jpg"
        Image.new("RGB", (20, 20), (20, 40, 220)).save(first)
        Image.new("RGB", (20, 20), (220, 30, 20)).save(highest)
        sent: list[tuple[str, str]] = []
        client = WebhookClient(self.config, lambda _message: None)
        client._send = lambda event, body: sent.append((event, body))  # type: ignore[method-assign]

        client.notify_image_path("score-image", "最高分照片", highest, self.work_dir)

        self.assertEqual(len(sent), 1)
        payload = json.loads(sent[0][1])
        image_bytes = base64.b64decode(payload["image"])
        self.assertEqual(payload["md5"], hashlib.md5(image_bytes).hexdigest())
        self.assertTrue((self.work_dir / "post_img" / highest.name).exists())
        with Image.open(self.work_dir / "post_img" / "compressed.jpg") as image:
            red, _green, blue = image.convert("RGB").getpixel((10, 10))
        self.assertGreater(red, blue)

    def test_disabled_image_push_does_not_prepare_a_file(self) -> None:
        source = self.hdr_dir / "highest.jpg"
        Image.new("RGB", (20, 20), (220, 30, 20)).save(source)
        self.config["push_image"] = False
        client = WebhookClient(self.config, lambda _message: None)

        client.notify_image_path("score-image", "最高分照片", source, self.work_dir)

        self.assertFalse((self.work_dir / "post_img").exists())

    def test_network_failure_is_logged_without_raising(self) -> None:
        logs: list[str] = []
        client = WebhookClient(self.config, logs.append)
        with patch(
            "timelapse_manager.webhook.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            client.notify("score-result", "评分完成")

        self.assertTrue(any("webhook 推送失败" in message for message in logs))


if __name__ == "__main__":
    unittest.main()
