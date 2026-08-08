from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from timelapse_manager.album_naming import (
    date_album_path,
    label_sunset_album,
    rewrite_eternal_album_paths,
)
from timelapse_manager.errors import TaskError
from timelapse_manager.io_utils import load_yaml, save_yaml


class AlbumNamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "output"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_labels_date_and_time_directories_with_sunset_score(self) -> None:
        work_dir = self.root / "1900-01-01" / "0300-0900"
        work_dir.mkdir(parents=True)

        renamed = label_sunset_album(work_dir, self.root, 3)

        assert renamed is not None
        expected = (self.root / "1900-01-01-S3" / "0300-0900-S3").resolve()
        self.assertEqual(renamed.work_dir, expected)
        self.assertTrue(expected.is_dir())
        self.assertFalse(work_dir.exists())

    def test_date_directory_uses_highest_child_score(self) -> None:
        first = self.root / "1900-01-01" / "0300-0900"
        first.mkdir(parents=True)
        first_result = label_sunset_album(first, self.root, 3)
        assert first_result is not None
        second = first_result.date_dir / "1500-2100"
        second.mkdir()

        lower = label_sunset_album(second, self.root, 2)

        assert lower is not None
        self.assertEqual(lower.date_dir.name, "1900-01-01-S3")
        self.assertTrue((lower.date_dir / "1500-2100-S2").is_dir())
        third = lower.date_dir / "1000-1200"
        third.mkdir()
        higher = label_sunset_album(third, self.root, 5)
        assert higher is not None
        self.assertEqual(higher.date_dir.name, "1900-01-01-S5")
        self.assertTrue((higher.date_dir / "0300-0900-S3").is_dir())
        self.assertTrue((higher.date_dir / "1500-2100-S2").is_dir())

    def test_new_album_uses_existing_scored_date_container(self) -> None:
        scored = self.root / "1900-01-01-S4"
        scored.mkdir()
        (self.root / "1900-01-01").mkdir()

        selected = date_album_path(self.root, "1900-01-01")

        self.assertEqual(selected, scored.resolve())

    def test_rewrites_eternal_manifests_after_date_move(self) -> None:
        work_dir = self.root / "1900-01-01" / "0300-0900"
        work_dir.mkdir(parents=True)
        state_dir = Path(self.temp.name) / "state"
        queue_dir = state_dir / "queue"
        queue_dir.mkdir(parents=True)
        archive = state_dir / "archive.00000001.yaml"
        ready = queue_dir / "00000002.ready.yaml"
        save_yaml(archive, {"batch_dir": str(work_dir)})
        save_yaml(ready, {"batch_dir": str(work_dir.parent / "1500-2100")})
        renamed = label_sunset_album(work_dir, self.root, 4)
        assert renamed is not None

        changed = rewrite_eternal_album_paths(
            state_dir,
            queue_dir,
            renamed.old_date_dir,
            renamed.date_dir,
        )

        self.assertEqual(changed, 2)
        self.assertEqual(
            load_yaml(archive)["batch_dir"],
            str(renamed.date_dir / "0300-0900"),
        )
        self.assertEqual(
            load_yaml(ready)["batch_dir"],
            str(renamed.date_dir / "1500-2100"),
        )

    def test_unmanaged_or_conflicting_directory_is_not_overwritten(self) -> None:
        unmanaged = self.root / "custom" / "album"
        unmanaged.mkdir(parents=True)
        self.assertIsNone(label_sunset_album(unmanaged, self.root, 3))
        work_dir = self.root / "1900-01-01" / "0300-0900"
        work_dir.mkdir(parents=True)
        (work_dir.parent / "0300-0900-S3").mkdir()
        with self.assertRaisesRegex(TaskError, "目标目录已存在"):
            label_sunset_album(work_dir, self.root, 3)


if __name__ == "__main__":
    unittest.main()
