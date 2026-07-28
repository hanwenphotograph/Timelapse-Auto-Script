from __future__ import annotations

import sys
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from timelapse_manager.app_icon import (
    application_icon_path,
    apply_application_icon,
    prepare_application_icon,
)
from timelapse_manager import gui


class AppIconTests(unittest.TestCase):
    def test_icon_asset_has_expected_brand_pixels(self) -> None:
        with Image.open(application_icon_path()) as icon:
            self.assertEqual(icon.size, (1024, 1024))
            self.assertEqual(icon.mode, "RGBA")
            self.assertEqual(icon.getpixel((0, 0))[3], 0)
            self.assertEqual(icon.getpixel((96, 512))[3], 0)
            self.assertEqual(icon.getpixel((128, 512))[:3], (57, 119, 246))

    def test_platform_icon_containers_include_multiple_sizes(self) -> None:
        asset_dir = application_icon_path().parent
        with Image.open(asset_dir / "timelapse-manager.ico") as icon:
            self.assertEqual(icon.format, "ICO")
            self.assertIn((16, 16), icon.info["sizes"])
            self.assertIn((256, 256), icon.info["sizes"])
        with Image.open(asset_dir / "timelapse-manager.icns") as icon:
            self.assertEqual(icon.format, "ICNS")
            self.assertIn((32, 32, 2), icon.info["sizes"])
            self.assertIn((512, 512, 2), icon.info["sizes"])

    def test_tk_window_receives_icon_photo(self) -> None:
        root = Mock()
        photo = object()
        with (
            patch("timelapse_manager.app_icon.tk.PhotoImage", return_value=photo),
            patch.object(sys, "platform", "linux"),
        ):
            apply_application_icon(root)

        root.iconphoto.assert_called_once_with(True, photo)
        self.assertIs(root._timelapse_icon_photo, photo)

    def test_macos_dock_icon_is_applied(self) -> None:
        root = Mock()
        with (
            patch("timelapse_manager.app_icon.tk.PhotoImage"),
            patch.object(sys, "platform", "darwin"),
            patch("timelapse_manager.app_icon._set_macos_dock_icon") as set_dock_icon,
            patch(
                "timelapse_manager.app_icon._reveal_macos_dock_icon"
            ) as reveal_dock_icon,
        ):
            apply_application_icon(root, reveal_macos_icon=True)

        self.assertEqual(set_dock_icon.call_count, 2)
        set_dock_icon.assert_called_with(application_icon_path())
        reveal_dock_icon.assert_called_once_with()
        root.after.assert_called_once_with(
            100,
            set_dock_icon,
            application_icon_path(),
        )

    def test_macos_icon_is_prepared_before_tk_root_creation(self) -> None:
        events: list[str] = []
        root = Mock()
        with (
            patch.object(
                gui,
                "prepare_application_icon",
                side_effect=lambda: events.append("prepare") or True,
            ),
            patch.object(
                gui,
                "apply_base_theme",
                side_effect=lambda: events.append("theme"),
            ),
            patch.object(
                gui.ctk,
                "CTk",
                side_effect=lambda: events.append("root") or root,
            ),
            patch.object(
                gui,
                "apply_application_icon",
                side_effect=lambda _root, **_kwargs: events.append("apply"),
            ) as apply_icon,
            patch.object(gui, "ManagerService"),
            patch.object(gui, "TimelapseApp"),
        ):
            gui.launch_gui()

        self.assertEqual(events, ["prepare", "theme", "root", "apply"])
        apply_icon.assert_called_once_with(
            root,
            reveal_macos_icon=True,
        )
        root.mainloop.assert_called_once_with()

    def test_prepare_icon_is_a_noop_outside_macos(self) -> None:
        with (
            patch.object(sys, "platform", "linux"),
            patch("timelapse_manager.app_icon._hide_macos_dock_icon") as hide_dock_icon,
        ):
            prepared = prepare_application_icon()

        self.assertFalse(prepared)
        hide_dock_icon.assert_not_called()

    def test_prepare_icon_hides_source_process_on_macos(self) -> None:
        with (
            patch.object(sys, "platform", "darwin"),
            patch.object(sys, "frozen", False, create=True),
            patch(
                "timelapse_manager.app_icon._hide_macos_dock_icon",
                return_value=True,
            ) as hide_dock_icon,
        ):
            prepared = prepare_application_icon()

        self.assertTrue(prepared)
        hide_dock_icon.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
