from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PIL import Image

from timelapse_manager.app_icon import (
    application_icon_path,
    apply_application_icon,
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
        with patch(
            "timelapse_manager.app_icon.tk.PhotoImage",
            return_value=photo,
        ):
            apply_application_icon(root)

        root.iconphoto.assert_called_once_with(True, photo)
        self.assertIs(root._timelapse_icon_photo, photo)

    def test_icon_is_applied_after_tk_root_creation(self) -> None:
        events: list[str] = []
        root = Mock()
        with (
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

        self.assertEqual(events, ["theme", "root", "apply"])
        apply_icon.assert_called_once_with(root)
        root.mainloop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
