from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from timelapse_manager import runtime_check


class RuntimeCheckTests(unittest.TestCase):
    def test_pip_check_locates_modules_without_importing_them(self) -> None:
        with (
            patch.object(
                runtime_check.importlib.util, "find_spec", return_value=object()
            ),
            patch.object(runtime_check.importlib, "import_module") as import_module,
        ):
            self.assertTrue(runtime_check.pip_dependencies_ready())
        import_module.assert_not_called()

    def test_pip_check_reports_a_missing_module(self) -> None:
        def find_spec(name: str):
            return None if name == "customtkinter" else object()

        with patch.object(
            runtime_check.importlib.util, "find_spec", side_effect=find_spec
        ):
            self.assertFalse(runtime_check.pip_dependencies_ready())

    def test_tkinter_check_uses_a_display_free_tcl_interpreter(self) -> None:
        interpreter = SimpleNamespace(eval=lambda script: "8.6.18")
        tkinter = SimpleNamespace(Tcl=lambda: interpreter)
        with patch.object(
            runtime_check.importlib, "import_module", return_value=tkinter
        ):
            self.assertTrue(runtime_check.tkinter_ready())

    def test_tkinter_check_handles_a_missing_native_extension(self) -> None:
        with patch.object(
            runtime_check.importlib,
            "import_module",
            side_effect=ModuleNotFoundError("No module named '_tkinter'"),
        ):
            self.assertFalse(runtime_check.tkinter_ready())

    def test_homebrew_formula_matches_the_base_python_version(self) -> None:
        formula = runtime_check.homebrew_tk_formula(
            "/opt/homebrew/Cellar/python@3.10/3.10.20_4/bin/python3.10",
            (3, 10),
        )
        self.assertEqual(formula, "python-tk@3.10")

    def test_non_homebrew_python_has_no_formula(self) -> None:
        formula = runtime_check.homebrew_tk_formula(
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
            (3, 12),
        )
        self.assertIsNone(formula)


if __name__ == "__main__":
    unittest.main()
