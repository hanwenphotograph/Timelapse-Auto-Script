"""Configuration page layout and actions, separated from the main window."""

from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from timelapse_manager.io_utils import yaml_text
from timelapse_manager.ui.configuration.fields import PROJECT_GROUPS, WEBHOOK_GROUPS
from timelapse_manager.ui.configuration.form import ConfigForm
from timelapse_manager.ui.theme import ACCENT, BORDER, MUTED, SURFACE
from timelapse_manager.ui.widgets import action_button


class ConfigPageMixin:
    def _build_config_page(self) -> None:
        page = self.page_frames["config"]
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        toolbar = ctk.CTkFrame(
            page,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.grid_columnconfigure(1, weight=1)
        self.config_selector = ctk.CTkSegmentedButton(
            toolbar,
            values=["项目配置", "Webhook"],
            command=self._config_selected,
            selected_color=ACCENT,
            height=34,
        )
        self.config_selector.grid(row=0, column=0, padx=14, pady=12)
        self.config_selector.set("项目配置")
        self.config_path_label = ctk.CTkLabel(
            toolbar, text="", text_color=MUTED, anchor="e"
        )
        self.config_path_label.grid(row=0, column=1, sticky="e", padx=12)
        self.test_webhook_button = action_button(
            toolbar, "测试文本和图片", self.test_webhook, width=126
        )
        self.test_webhook_button.grid(row=0, column=2, padx=(0, 14), pady=8)
        self.config_forms = {}
        for kind, groups in (("project", PROJECT_GROUPS), ("webhook", WEBHOOK_GROUPS)):
            form = ConfigForm(page, groups)
            form.grid(row=1, column=0, sticky="nsew")
            form.load(self.service.config_manager.read_data(kind))
            self.config_forms[kind] = form
        self.config_forms["webhook"].grid_remove()
        buttons = ctk.CTkFrame(page, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        buttons.grid_columnconfigure(2, weight=1)
        action_button(buttons, "从磁盘重读", self.reload_config, width=112).grid(
            row=0, column=0
        )
        action_button(
            buttons, "打开所在目录", self.open_config_location, width=112
        ).grid(row=0, column=1, padx=8)
        action_button(
            buttons, "保存配置", self.save_config, primary=True, width=120
        ).grid(row=0, column=3, sticky="e")
        self._update_config_path()
        self._update_config_actions()

    def _config_selected(self, label: str) -> None:
        self.config_forms[self._current_config_kind].grid_remove()
        self._current_config_kind = "project" if label == "项目配置" else "webhook"
        self.config_forms[self._current_config_kind].grid()
        self._update_config_path()
        self._update_config_actions()

    def reload_config(self, kind: str | None = None, *, quiet: bool = False) -> None:
        target = kind or self._current_config_kind
        try:
            self.service.reload()
            self.config_forms[target].load(
                self.service.config_manager.read_data(target)
            )
        except Exception as exc:
            if not quiet:
                messagebox.showerror("读取配置失败", str(exc), parent=self.root)
            return
        self._update_config_path()
        if not quiet:
            self._set_status("已从磁盘重新读取配置")

    def save_config(self) -> None:
        self._save_current_config(show_confirmation=True)

    def _save_current_config(self, *, show_confirmation: bool) -> bool:
        kind = self._current_config_kind
        try:
            content = self.config_forms[kind].values()
            self.service.config_manager.save_text(kind, yaml_text(content))
            self.service.reload()
        except Exception as exc:
            messagebox.showerror("配置保存失败", str(exc), parent=self.root)
            return False
        self.refresh_all()
        self._set_status("配置已校验并保存")
        if show_confirmation:
            messagebox.showinfo(
                "配置已保存", "配置已通过校验并保存。", parent=self.root
            )
        return True

    def test_webhook(self) -> None:
        if self._current_config_kind == "webhook" and self._save_current_config(
            show_confirmation=False
        ):
            self._async_action("Webhook 测试推送", self.service.test_webhook)

    def _current_config_path(self) -> Path:
        return (
            self.service.paths.config_file
            if self._current_config_kind == "project"
            else self.service.paths.webhook_file
        )

    def _update_config_path(self) -> None:
        self.config_path_label.configure(text=str(self._current_config_path()))

    def _update_config_actions(self) -> None:
        if self._current_config_kind == "webhook":
            self.test_webhook_button.grid()
        else:
            self.test_webhook_button.grid_remove()

    def open_config_location(self) -> None:
        self._open_path(self._current_config_path().parent)
