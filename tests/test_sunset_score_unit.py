from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from timelapse_manager.sunset_score.cache import (
    CacheMismatchError,
    validate_score_inventory,
)
from timelapse_manager.sunset_score.score_file import read_score_file
from timelapse_manager.sunset_score.service import SunsetScoreService


REPOSITORY = Path(__file__).resolve().parents[1]
FAKE_SUNSET = REPOSITORY / "tests" / "fixtures" / "fake_sunsetscore.py"


def command_for(script: Path) -> str:
    return f'"{sys.executable}" "{script}"'


def run_fake_score(
    directory: Path,
    scores: str,
    *,
    failed_indexes: str = "",
) -> Path:
    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_SUNSET_SCORES": scores,
            "FAKE_SUNSET_FAILED_INDEXES": failed_indexes,
        }
    )
    subprocess.run(
        [sys.executable, str(FAKE_SUNSET), str(directory), "--interval", "1"],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return directory / ".sunsetscore-score.json"


class FakeWebhook:
    def __init__(self):
        self.events: list[tuple[str, str, object]] = []

    def notify(self, event: str, content: str) -> None:
        self.events.append(("text", event, content))

    def notify_image_path(
        self, event: str, content: str, source: Path, _work_dir: Path
    ) -> None:
        self.events.append(("image", event, source))


class CacheRuntime:
    def __init__(self):
        self.webhook = FakeWebhook()
        self.logs: list[str] = []

    def log(self, message: str) -> None:
        self.logs.append(message)

    def set_phase(self, phase: str, message: str) -> None:
        self.logs.append(f"{phase}: {message}")


class SunsetScoreCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp.name) / "work"
        self.hdr_dir = self.work_dir / "hdr_enfuse"
        self.hdr_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _images(self, count: int) -> None:
        for index in range(1, count + 1):
            (self.hdr_dir / f"frame-{index:04d}.jpg").write_bytes(b"image")

    def test_cache_rejects_path_traversal(self) -> None:
        self._images(1)
        path = run_fake_score(self.hdr_dir, "1")
        document = json.loads(path.read_text(encoding="utf-8"))
        document["sample_scores"][0]["photo"] = "../outside.jpg"
        path.write_text(json.dumps(document), encoding="utf-8")
        score = read_score_file(path)
        with self.assertRaisesRegex(CacheMismatchError, "清单不一致"):
            validate_score_inventory(
                score,
                self.hdr_dir,
                interval=1,
                application_version="0.9.0",
                require_retry_safe=True,
            )

    def test_partial_negative_cache_is_not_retry_safe(self) -> None:
        self._images(3)
        path = run_fake_score(self.hdr_dir, "1,1,1", failed_indexes="2")
        score = read_score_file(path)
        with self.assertRaisesRegex(CacheMismatchError, "失败样本"):
            validate_score_inventory(
                score,
                self.hdr_dir,
                interval=1,
                application_version="0.9.0",
                require_retry_safe=True,
            )

    def test_partial_positive_cache_is_retry_safe(self) -> None:
        self._images(3)
        path = run_fake_score(self.hdr_dir, "4,4,4", failed_indexes="2")
        score = read_score_file(path)

        highest = validate_score_inventory(
            score,
            self.hdr_dir,
            interval=1,
            application_version="0.9.0",
            require_retry_safe=True,
        )

        self.assertTrue(score.has_sunset)
        self.assertEqual(highest.name, "frame-0001.jpg")

    def test_cache_rejects_changed_interval_and_inventory(self) -> None:
        self._images(2)
        path = run_fake_score(self.hdr_dir, "1,1")
        score = read_score_file(path)
        with self.assertRaisesRegex(CacheMismatchError, "采样间隔"):
            validate_score_inventory(
                score,
                self.hdr_dir,
                interval=2,
                application_version="0.9.0",
                require_retry_safe=True,
            )
        (self.hdr_dir / "frame-0003.jpg").write_bytes(b"image")
        with self.assertRaisesRegex(CacheMismatchError, "图片总数"):
            validate_score_inventory(
                score,
                self.hdr_dir,
                interval=1,
                application_version="0.9.0",
                require_retry_safe=True,
            )

    def test_service_reuses_cache_and_selects_first_highest(self) -> None:
        self._images(2)
        run_fake_score(self.hdr_dir, "4,4")
        runtime = CacheRuntime()
        service = SunsetScoreService(
            runtime,  # type: ignore[arg-type]
            command_for(FAKE_SUNSET),
            1,
            processing_enabled=True,
        )

        decision = service.process(self.work_dir, "缓存测试")

        assert decision is not None
        self.assertTrue(decision.retained_hdr)
        self.assertEqual(decision.highest_path.name, "frame-0001.jpg")
        self.assertEqual(
            [event[:2] for event in runtime.webhook.events],
            [("text", "sunset-score-result"), ("image", "sunset-score-image")],
        )
        self.assertIn("复用有效缓存", "\n".join(runtime.logs))

    def test_negative_result_deletes_hdr_directory(self) -> None:
        self._images(1)
        run_fake_score(self.hdr_dir, "1")
        runtime = CacheRuntime()
        service = SunsetScoreService(
            runtime,  # type: ignore[arg-type]
            command_for(FAKE_SUNSET),
            1,
            processing_enabled=True,
        )

        decision = service.process(self.work_dir, "删除测试")

        assert decision is not None
        self.assertFalse(decision.retained_hdr)
        self.assertFalse(self.hdr_dir.exists())


if __name__ == "__main__":
    unittest.main()
