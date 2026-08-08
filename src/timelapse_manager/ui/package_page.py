"""Package-management page controller."""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk
from tkinter import messagebox

from timelapse_manager.dependency_manager import DependencyManager, DependencyStatus
from timelapse_manager.ui.package_layout import build_package_layout


class PackagePage:
    def __init__(
        self,
        page: ctk.CTkFrame,
        root: ctk.CTk,
        manager: DependencyManager,
        notify: Callable[[str, str], None],
    ) -> None:
        self.root = root
        self.manager = manager
        self.notify = notify
        self._closed = False
        self._busy = False
        self._statuses = manager.placeholders()
        layout = build_package_layout(
            page,
            self._statuses,
            str(manager.dependency_root),
            self.refresh,
            self.install,
        )
        self.summary = layout.summary
        self.install_location = layout.install_location
        self.activity = layout.activity
        self.refresh_button = layout.refresh_button
        self.progress = layout.progress
        self.progress_value = layout.progress_value
        self._rows = layout.rows
        self._apply_statuses(self._statuses)

    def refresh(self) -> None:
        if self._busy or self._closed:
            return
        self._set_busy(True, "正在检测依赖…")

        def progress(completed: int, total: int, name: str) -> None:
            self._after(lambda: self._scan_progress(completed, total, name))

        def work() -> None:
            try:
                statuses = self.manager.inspect(progress)
            except Exception as exc:
                self._after(lambda error=exc: self._inspect_finished(None, error))
            else:
                self._after(lambda: self._inspect_finished(statuses, None))

        threading.Thread(target=work, name="gui-dependency-scan", daemon=True).start()

    def install(self, identifier: str) -> None:
        if self._busy or self._closed:
            return
        branch = self._rows[identifier].selected_branch
        confirmation = self.manager.confirmation(identifier, branch)
        if not confirmation:
            messagebox.showinfo(
                "需要手动安装",
                "当前平台没有可用的自动安装方案，请按对应项目文档手动安装。",
                parent=self.root,
            )
            return
        if not messagebox.askyesno("确认安装", confirmation, parent=self.root):
            return
        status = next(
            item for item in self._statuses if item.spec.identifier == identifier
        )
        label = status.spec.name
        self._set_busy(True, f"正在安装 {label}…")
        self.notify(f"正在安装 {label}", "busy")

        def output(message: str) -> None:
            self._after(lambda value=message: self.activity.configure(text=value[-64:]))

        def progress(value: float) -> None:
            self._after(lambda: self._set_progress(value))

        def work() -> None:
            try:
                self.manager.install(
                    identifier,
                    output,
                    progress,
                    branch=branch,
                )
            except Exception as exc:
                self._after(lambda error=exc: self._install_finished(label, error))
            else:
                self._after(lambda: self._install_finished(label, None))

        threading.Thread(
            target=work, name=f"gui-install-{identifier}", daemon=True
        ).start()

    def _inspect_finished(
        self,
        statuses: list[DependencyStatus] | None,
        error: Exception | None,
    ) -> None:
        if error:
            self._set_busy(False, "")
            self.activity.configure(text=f"检测失败：{error}")
            self.notify(f"依赖检测失败：{error}", "error")
            return
        assert statuses is not None
        self._statuses = statuses
        self._set_busy(False, "")
        self.notify("依赖状态已刷新", "success")

    def _scan_progress(self, completed: int, total: int, name: str) -> None:
        self._set_progress(completed / total if total else 0)
        self.activity.configure(text=f"正在检测 {name} · {completed}/{total}")

    def _install_finished(self, label: str, error: Exception | None) -> None:
        self._set_busy(False, "")
        if error:
            messagebox.showerror(f"{label} 安装失败", str(error), parent=self.root)
            self.notify(f"{label} 安装失败", "error")
        else:
            self.notify(f"{label} 安装完成", "success")
        self.refresh()

    def _apply_statuses(self, statuses: list[DependencyStatus]) -> None:
        for status in statuses:
            self._rows[status.spec.identifier].update_status(status, busy=self._busy)
        if any(item.state == "checking" for item in statuses):
            self.summary.configure(text=f"正在检测 {len(statuses)} 项依赖")
            if not self._busy:
                self._set_progress(0)
            return
        ready = sum(item.ready for item in statuses)
        missing_required = sum(
            item.spec.required and not item.ready for item in statuses
        )
        self.summary.configure(
            text=f"已就绪 {ready} / {len(statuses)} · 必需项未就绪 {missing_required}"
        )
        if not self._busy:
            self._set_progress(ready / len(statuses) if statuses else 0)

    def _set_busy(self, busy: bool, activity: str) -> None:
        self._busy = busy
        self.activity.configure(text=activity)
        self.refresh_button.configure(state="disabled" if busy else "normal")
        if busy:
            self._set_progress(0)
        self._apply_statuses(self._statuses)

    def _set_progress(self, value: float) -> None:
        normalized = min(1.0, max(0.0, value))
        self.progress.set(normalized)
        self.progress_value.configure(text=f"{normalized:.0%}")

    def _after(self, operation: Callable[[], None]) -> None:
        if self._closed:
            return
        try:
            self.root.after(0, operation)
        except (tk.TclError, RuntimeError):
            pass

    def close(self) -> None:
        self._closed = True
