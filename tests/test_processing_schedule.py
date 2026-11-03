from __future__ import annotations

import unittest
from datetime import datetime

from timelapse_manager.errors import ConfigError
from timelapse_manager.processing.schedule import (
    processing_due_at,
    processing_ready,
    validate_processing_time,
)


def local(value):
    return datetime.fromisoformat(value).astimezone()


class ProcessingScheduleTests(unittest.TestCase):
    def test_evening_material_waits_until_midnight(self):
        project = {"photo_processing": {"mode": "scheduled", "start_at": "00:00"}}
        ready = local("2026-11-03T20:00:00").isoformat()
        self.assertEqual(
            processing_due_at(project, ready), local("2026-11-04T00:00:00")
        )
        self.assertFalse(processing_ready(project, ready, local("2026-11-03T23:59:59")))
        self.assertTrue(processing_ready(project, ready, local("2026-11-04T00:00:00")))

    def test_material_after_daily_start_waits_for_next_day(self):
        project = {"photo_processing": {"mode": "scheduled", "start_at": "02:30"}}
        ready = local("2026-11-03T02:31:00").isoformat()
        self.assertEqual(
            processing_due_at(project, ready), local("2026-11-04T02:30:00")
        )

    def test_restart_after_missed_start_processes_backlog(self):
        project = {"photo_processing": {"mode": "scheduled", "start_at": "00:00"}}
        ready = local("2026-11-01T20:00:00").isoformat()
        self.assertTrue(processing_ready(project, ready, local("2026-11-03T12:00:00")))

    def test_immediate_mode_and_legacy_config_are_ready(self):
        ready = local("2026-11-03T20:00:00").isoformat()
        for project in (
            {},
            {"photo_processing": {"mode": "immediate", "start_at": "00:00"}},
        ):
            self.assertTrue(
                processing_ready(project, ready, local("2026-11-03T20:00:00"))
            )

    def test_invalid_modes_and_times_are_rejected(self):
        for value in (
            None,
            {},
            {"mode": "other", "start_at": "00:00"},
            *(
                {"mode": "scheduled", "start_at": value}
                for value in ("24:00", "12:60", "0:00", "00:00:00", None, 0)
            ),
        ):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                validate_processing_time(value)
