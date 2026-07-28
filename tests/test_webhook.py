from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from timelapse_manager.errors import WebhookError
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
            "body": '{"msgtype":"text","text":{"content":"__CONTENT__"}}',
            "push_image": True,
            "image_body": (
                '{"msgtype":"image","image":'
                '{"base64":"__IMGBASE64__","md5":"__IMGMD5__"}}'
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
        self.assertEqual(payload["msgtype"], "image")
        image_payload = payload["image"]
        image_bytes = base64.b64decode(image_payload["base64"])
        self.assertEqual(
            image_payload["md5"],
            hashlib.md5(image_bytes).hexdigest(),
        )
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

    def test_test_push_uses_wecom_text_body_while_notifications_are_disabled(
        self,
    ) -> None:
        self.config["enabled"] = False
        self.config["push_image"] = False
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"errcode":0,"errmsg":"ok"}'
        client = WebhookClient(self.config, lambda _message: None)

        with patch(
            "timelapse_manager.webhook.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            result = client.test_push('包含"引号"\n和换行')

        self.assertEqual(urlopen.call_count, 2)
        text_request = urlopen.call_args_list[0].args[0]
        text_payload = json.loads(text_request.data.decode("utf-8"))
        self.assertEqual(text_payload["msgtype"], "text")
        self.assertEqual(text_payload["text"]["content"], '包含"引号"\n和换行')

        image_request = urlopen.call_args_list[1].args[0]
        image_payload = json.loads(image_request.data.decode("utf-8"))["image"]
        image_bytes = base64.b64decode(image_payload["base64"])
        self.assertEqual(
            image_payload["md5"],
            hashlib.md5(image_bytes).hexdigest(),
        )
        with Image.open(BytesIO(image_bytes)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (640, 360))
        self.assertEqual(result, "文本：ok；图片：ok")

    def test_wecom_error_response_is_logged_as_failure(self) -> None:
        logs: list[str] = []
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"errcode":93000,"errmsg":"invalid webhook url"}'
        client = WebhookClient(self.config, logs.append)

        with patch(
            "timelapse_manager.webhook.urllib.request.urlopen",
            return_value=response,
        ):
            client.notify("score-result", "评分完成")

        self.assertTrue(any("企业微信返回错误 93000" in message for message in logs))

    def test_test_push_accepts_a_generic_success_response(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"<html>proxy error</html>"
        client = WebhookClient(self.config, lambda _message: None)

        with patch(
            "timelapse_manager.webhook.urllib.request.urlopen",
            return_value=response,
        ):
            result = client.test_push()

        self.assertEqual(
            result,
            "文本：HTTP 请求成功；图片：HTTP 请求成功",
        )

    def test_test_push_validates_image_template_before_sending(self) -> None:
        self.config["image_body"] = '{"image":"__IMGBASE64__"}'
        client = WebhookClient(self.config, lambda _message: None)

        with patch(
            "timelapse_manager.webhook.urllib.request.urlopen",
        ) as urlopen:
            with self.assertRaisesRegex(WebhookError, "__IMGMD5__"):
                client.test_push()

        urlopen.assert_not_called()

    def test_test_push_requires_a_url_even_when_disabled(self) -> None:
        self.config["enabled"] = False
        self.config["url"] = ""
        client = WebhookClient(self.config, lambda _message: None)

        with self.assertRaisesRegex(WebhookError, "URL 不能为空"):
            client.test_push()


if __name__ == "__main__":
    unittest.main()
