from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from timelapse_manager.config import ConfigManager, DEFAULT_PROJECT_CONFIG
from timelapse_manager.errors import ConfigError
from timelapse_manager.io_utils import yaml_text
from timelapse_manager.paths import AppPaths
from timelapse_manager.ui.configuration.fields import Field, PROJECT_GROUPS
from timelapse_manager.ui.configuration.form import ConfigForm, parse_field, read_path
from timelapse_manager.ui.configuration.page import ConfigPageMixin


class ConfigFormTests(unittest.TestCase):
    def test_form_fields_cover_all_editable_project_values(self):
        def paths(data, prefix=""):
            return {
                path
                for key, value in data.items()
                for path in (
                    paths(value, prefix + key + ".")
                    if isinstance(value, dict)
                    else {prefix + key}
                )
            }

        fields = {field.path for _, group in PROJECT_GROUPS for field in group}
        self.assertEqual(fields, paths(DEFAULT_PROJECT_CONFIG) - {"schema_version"})

    def test_typed_values_and_invalid_numbers(self):
        self.assertEqual(
            parse_field(Field("a", "a", "mode"), "自定义时间"), "scheduled"
        )
        self.assertEqual(parse_field(Field("a", "a", "int"), "10"), 10)
        for kind, value in (
            ("int", "1.5"),
            ("float", "nan"),
            ("float", "inf"),
            ("float", ""),
        ):
            with self.subTest(kind=kind, value=value), self.assertRaises(ConfigError):
                parse_field(Field("a", "a", kind), value)

    def test_form_serialization_preserves_unknown_keys(self):
        form = ConfigForm.__new__(ConfigForm)
        form.base = {
            "schema_version": 1,
            "extension": {"keep": True},
            "photo_processing": {"mode": "immediate"},
        }
        form.fields = {
            "photo_processing.mode": Field("photo_processing.mode", "mode", "mode")
        }
        form.controls = {"photo_processing.mode": Mock()}
        form.controls["photo_processing.mode"].get.return_value = "自定义时间"
        data = form.values()
        self.assertEqual(data["extension"], {"keep": True})
        self.assertEqual(data["photo_processing"]["mode"], "scheduled")
        self.assertEqual(form.base["photo_processing"]["mode"], "immediate")

    def test_read_data_does_not_bake_environment_override_into_form(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ConfigManager(AppPaths.discover(Path(directory)))
            with patch.dict("os.environ", {"CAPTURE_INTERVAL_SECONDS": "17"}):
                self.assertEqual(manager.load().project["capture_interval_seconds"], 17)
                self.assertEqual(
                    manager.read_data("project")["capture_interval_seconds"], 6
                )

    def test_switching_forms_keeps_unsaved_controls(self):
        app = ConfigPageMixin()
        app._current_config_kind = "project"
        app.config_forms = {"project": Mock(), "webhook": Mock()}
        app._update_config_path = Mock()
        app._update_config_actions = Mock()
        app._config_selected("Webhook")
        app._config_selected("项目配置")
        for form in app.config_forms.values():
            form.load.assert_not_called()

    def test_form_values_round_trip_through_configuration_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ConfigManager(AppPaths.discover(Path(directory)))
            data = deepcopy(DEFAULT_PROJECT_CONFIG)
            for _, fields in PROJECT_GROUPS:
                for field in fields:
                    value = read_path(data, field.path)
                    if field.kind not in {"mode", "bool"}:
                        self.assertEqual(parse_field(field, str(value)), value)
            data["photo_processing"] = {"mode": "scheduled", "start_at": "00:00"}
            manager.save_text("project", yaml_text(data))
            self.assertEqual(
                manager.load().project["photo_processing"], data["photo_processing"]
            )
