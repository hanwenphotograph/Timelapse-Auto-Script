"""Main CustomTkinter application for Timelapse Manager."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from timelapse_manager.service import ManagerService
from timelapse_manager.task_store import ACTIVE_STATUSES
from timelapse_manager.ui.dialogs import NewTaskDialog, YamlEditorDialog
from timelapse_manager.ui.progress import compact_timestamp, task_progress_label
from timelapse_manager.ui.table import ModernTable
from timelapse_manager.ui.theme import (
    ACCENT,
    BACKGROUND,
    BORDER,
    DANGER,
    FONT_FAMILY,
    MONOSPACE_FONT_FAMILY,
    MUTED,
    SIDEBAR,
    SUCCESS,
    SURFACE,
    SURFACE_ALT,
    TEXT,
    WARNING,
    apply_font_defaults,
    apply_status_tags,
    apply_table_style,
)
from timelapse_manager.ui.widgets import SummaryCard, action_button


PAGE_META = {
    "overview": ("运行总览", "集中查看任务与后台进程的实时状态"),
    "tasks": ("任务管理", "创建任务并手动控制延时摄影工作流"),
    "processes": ("进程监控", "查看和管理由程序启动的受控进程"),
    "config": ("配置中心", "双向读取、校验和保存项目 YAML 配置"),
    "logs": ("运行日志", "按任务查看最新日志和错误信息"),
}


def build_mode_label() -> str:
    mode = os.environ.get("TIMELAPSE_MANAGER_BUILD_MODE", "debug").lower()
    return "Release" if mode == "release" else "Debug"

STATUS_TEXT = {
    "idle": "待启动",
    "starting": "启动中",
    "running": "运行中",
    "finishing": "收尾中",
    "stopping": "停止中",
    "completed": "已完成",
    "failed": "失败",
    "stopped": "已停止",
    "exited": "已退出",
}

ROLE_TEXT = {
    "runner": "任务工作进程",
    "camera": "相机拍摄",
    "bracketlapse": "后期处理",
    "archive": "归档",
}


class TimelapseApp:
    REFRESH_MS = 1500

    def __init__(self, root: ctk.CTk, service: ManagerService) -> None:
        self.root = root
        self.service = service
        self.root.title(f"Timelapse Manager - {build_mode_label()}")
        self.root.geometry("1360x860")
        self.root.minsize(1180, 720)
        self.root.configure(fg_color=BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        apply_font_defaults(self.root)

        self._closed = False
        self._busy = 0
        self._active_page = "overview"
        self._current_config_kind = "project"
        self._config_drafts: dict[str, str] = {}
        self._task_ids: list[str] = []
        self._tables: list[ModernTable] = []

        self.status_value = tk.StringVar(value="就绪")
        self.selected_task_value = tk.StringVar(value="尚未选择任务")
        self.log_task_value = tk.StringVar(value="")
        self.appearance_value = tk.StringVar(value="跟随系统")

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self._build_ui()
        self._apply_tree_theme()
        self.show_page("overview")
        self.reload_config("project", quiet=True)
        self.refresh_all()
        self.root.after(self.REFRESH_MS, self._periodic_refresh)

    def _build_ui(self) -> None:
        self._build_sidebar()
        self.main = ctk.CTkFrame(
            self.root,
            fg_color=BACKGROUND,
            corner_radius=0,
        )
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self._build_header()
        self.page_container = ctk.CTkFrame(self.main, fg_color="transparent")
        self.page_container.grid(row=1, column=0, sticky="nsew", padx=28, pady=(4, 18))
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

        self.page_frames: dict[str, ctk.CTkFrame] = {}
        for key in PAGE_META:
            page = ctk.CTkFrame(self.page_container, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            self.page_frames[key] = page

        self._build_overview_page()
        self._build_tasks_page()
        self._build_processes_page()
        self._build_config_page()
        self._build_logs_page()
        self._build_status_bar()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self.root,
            width=226,
            corner_radius=0,
            fg_color=SIDEBAR,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(2, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 28))
        brand.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            brand,
            text="TL",
            width=44,
            height=44,
            corner_radius=12,
            fg_color=ACCENT,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
        ).grid(row=0, column=0, rowspan=2, sticky="w")
        ctk.CTkLabel(
            brand,
            text="Timelapse",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=17, weight="bold"),
            anchor="w",
        ).grid(row=0, column=1, sticky="sw", padx=(11, 0))
        ctk.CTkLabel(
            brand,
            text=f"Manager · {build_mode_label()}",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            anchor="w",
        ).grid(row=1, column=1, sticky="nw", padx=(11, 0))

        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="new", padx=13)
        nav.grid_columnconfigure(0, weight=1)
        nav_items = (
            ("overview", "运行总览"),
            ("tasks", "任务管理"),
            ("processes", "进程监控"),
            ("config", "配置中心"),
            ("logs", "运行日志"),
        )
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for row, (key, label) in enumerate(nav_items):
            button = ctk.CTkButton(
                nav,
                text=f"  {label}",
                command=lambda value=key: self.show_page(value),
                height=42,
                corner_radius=10,
                anchor="w",
                fg_color="transparent",
                hover_color=("#DCE6F7", "#1C2A42"),
                text_color=TEXT,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            )
            button.grid(row=row, column=0, sticky="ew", pady=3)
            self.nav_buttons[key] = button

        appearance = ctk.CTkFrame(
            sidebar,
            fg_color=SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        appearance.grid(row=3, column=0, sticky="sew", padx=16, pady=18)
        appearance.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            appearance,
            text="界面外观",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=13, pady=(12, 6))
        ctk.CTkOptionMenu(
            appearance,
            values=["跟随系统", "浅色", "深色"],
            variable=self.appearance_value,
            command=self._change_appearance,
            height=32,
            corner_radius=8,
            fg_color=SURFACE_ALT,
            button_color=ACCENT,
            button_hover_color=ACCENT,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=11),
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 15))
        header.grid_columnconfigure(0, weight=1)
        self.page_title = ctk.CTkLabel(
            header,
            text="",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=26, weight="bold"),
            anchor="w",
        )
        self.page_title.grid(row=0, column=0, sticky="w")
        self.page_subtitle = ctk.CTkLabel(
            header,
            text="",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            anchor="w",
        )
        self.page_subtitle.grid(row=1, column=0, sticky="w", pady=(3, 0))

        project = ctk.CTkFrame(
            header,
            fg_color=SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        project.grid(row=0, column=1, rowspan=2, padx=(18, 10), sticky="e")
        ctk.CTkLabel(
            project,
            text="项目目录",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=9, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(7, 0))
        ctk.CTkLabel(
            project,
            text=str(self.service.paths.root),
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
        ).pack(anchor="w", padx=12, pady=(0, 7))
        self.refresh_button = ctk.CTkButton(
            header,
            text="刷新",
            command=self.refresh_all,
            width=82,
            height=38,
            corner_radius=10,
            fg_color=ACCENT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        )
        self.refresh_button.grid(row=0, column=2, rowspan=2, sticky="e")

    def _build_status_bar(self) -> None:
        status = ctk.CTkFrame(
            self.main,
            height=34,
            corner_radius=0,
            fg_color=SURFACE,
            border_width=1,
            border_color=BORDER,
        )
        status.grid(row=2, column=0, sticky="ew")
        status.grid_propagate(False)
        status.grid_columnconfigure(1, weight=1)
        self.status_dot = ctk.CTkLabel(
            status,
            text="●",
            text_color=SUCCESS,
            width=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
        )
        self.status_dot.grid(row=0, column=0, padx=(20, 0))
        ctk.CTkLabel(
            status,
            textvariable=self.status_value,
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            anchor="w",
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(
            status,
            text="关闭窗口不会停止后台任务",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
        ).grid(row=0, column=2, padx=20)

    def _build_overview_page(self) -> None:
        page = self.page_frames["overview"]
        page.grid_rowconfigure(2, weight=1)
        page.grid_columnconfigure(0, weight=1)

        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew")
        for column in range(4):
            cards.grid_columnconfigure(column, weight=1, uniform="summary")
        self.summary_cards = {
            "total": SummaryCard(cards, "全部任务", "已保存的任务配置", ACCENT),
            "active": SummaryCard(cards, "活动任务", "正在运行或收尾", SUCCESS),
            "failed": SummaryCard(cards, "异常任务", "需要检查日志", DANGER),
            "processes": SummaryCard(cards, "受控进程", "当前存活进程", WARNING),
        }
        for column, card in enumerate(self.summary_cards.values()):
            card.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 6, 0 if column == 3 else 6),
            )

        table_header = ctk.CTkFrame(page, fg_color="transparent")
        table_header.grid(row=1, column=0, sticky="ew", pady=(24, 10))
        table_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            table_header,
            text="最近任务",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            table_header,
            text="新建任务",
            command=self.create_task,
            width=104,
            height=34,
            corner_radius=9,
            fg_color=ACCENT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).grid(row=0, column=1, sticky="e")

        self.overview_table = ModernTable(
            page,
            ("name", "preset", "status", "phase", "progress", "pid", "started"),
            {
                "name": "任务名称",
                "preset": "模式",
                "status": "状态",
                "phase": "当前阶段",
                "progress": "进度",
                "pid": "工作 PID",
                "started": "启动时间",
            },
            {
                "name": 260,
                "preset": 70,
                "status": 70,
                "phase": 180,
                "progress": 280,
                "pid": 70,
                "started": 210,
            },
        )
        self.overview_table.grid(row=2, column=0, sticky="nsew")
        self.overview_table.tree.bind(
            "<Double-1>", lambda _event: self._open_overview_task()
        )
        self._tables.append(self.overview_table)

    def _build_tasks_page(self) -> None:
        page = self.page_frames["tasks"]
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
        toolbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            toolbar,
            textvariable=self.selected_task_value,
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        ctk.CTkButton(
            toolbar,
            text="新建任务",
            command=self.create_task,
            width=100,
            height=34,
            corner_radius=9,
            fg_color=ACCENT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).grid(row=0, column=1, sticky="e", padx=14, pady=(10, 4))

        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        actions.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 13))
        task_actions = (
            ("编辑 YAML", self.edit_task, False, False, 96),
            ("启动任务", self.start_task, True, False, 92),
            ("立即收尾", lambda: self.control_task("finish_now"), False, False, 94),
            (
                "当前批次后收尾",
                lambda: self.control_task("finish_after_current"),
                False,
                False,
                132,
            ),
            ("强制停止", lambda: self.control_task("stop"), False, True, 94),
            ("重启", self.restart_task, False, False, 76),
            ("删除", self.delete_task, False, True, 76),
        )
        for index, (label, command, primary, danger, width) in enumerate(task_actions):
            action_button(
                actions,
                label,
                command,
                primary=primary,
                danger=danger,
                width=width,
            ).pack(side=tk.LEFT, padx=(0 if index == 0 else 7, 0))

        self.task_table = ModernTable(
            page,
            ("id", "name", "preset", "status", "phase", "pid", "started"),
            {
                "id": "任务 ID",
                "name": "名称",
                "preset": "模式",
                "status": "状态",
                "phase": "当前阶段",
                "pid": "工作 PID",
                "started": "启动时间",
            },
            {
                "id": 230,
                "name": 220,
                "preset": 70,
                "status": 70,
                "phase": 180,
                "pid": 70,
                "started": 210,
            },
        )
        self.task_table.grid(row=1, column=0, sticky="nsew")
        self.task_table.tree.bind("<Double-1>", lambda _event: self.edit_task())
        self.task_table.tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._selection_changed()
        )
        self._tables.append(self.task_table)

    def _build_processes_page(self) -> None:
        page = self.page_frames["processes"]
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
        toolbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            toolbar,
            text="仅显示由 Timelapse Manager 启动并跟踪的进程",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=14)
        action_button(
            toolbar,
            "终止所选进程",
            self.stop_process,
            danger=True,
            width=128,
        ).grid(row=0, column=1, padx=(8, 0), pady=10)
        action_button(toolbar, "刷新进程", self.refresh_processes, width=100).grid(
            row=0,
            column=2,
            padx=14,
            pady=10,
        )

        self.process_table = ModernTable(
            page,
            ("task", "role", "pid", "status", "started", "command"),
            {
                "task": "所属任务",
                "role": "进程角色",
                "pid": "PID",
                "status": "状态",
                "started": "启动时间",
                "command": "命令",
            },
            {
                "task": 220,
                "role": 100,
                "pid": 70,
                "status": 70,
                "started": 210,
                "command": 320,
            },
        )
        self.process_table.grid(row=1, column=0, sticky="nsew")
        self._tables.append(self.process_table)

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
            selected_hover_color=ACCENT,
            unselected_color=SURFACE_ALT,
            unselected_hover_color=BORDER,
            text_color=TEXT,
            corner_radius=9,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        )
        self.config_selector.grid(row=0, column=0, padx=14, pady=12)
        self.config_selector.set("项目配置")
        self.config_path_label = ctk.CTkLabel(
            toolbar,
            text="",
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            anchor="e",
        )
        self.config_path_label.grid(row=0, column=1, sticky="e", padx=(12, 16))

        editor_frame = ctk.CTkFrame(
            page,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        editor_frame.grid(row=1, column=0, sticky="nsew")
        editor_frame.grid_rowconfigure(0, weight=1)
        editor_frame.grid_columnconfigure(0, weight=1)
        self.config_text = ctk.CTkTextbox(
            editor_frame,
            wrap="none",
            corner_radius=11,
            border_width=0,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=ctk.CTkFont(family=MONOSPACE_FONT_FAMILY, size=12),
            undo=True,
        )
        self.config_text.grid(row=0, column=0, sticky="nsew", padx=9, pady=(9, 4))
        buttons = ctk.CTkFrame(editor_frame, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=10, pady=(6, 10))
        buttons.grid_columnconfigure(2, weight=1)
        action_button(buttons, "从磁盘重读", self.reload_config, width=112).grid(
            row=0, column=0, sticky="w"
        )
        action_button(
            buttons, "打开所在目录", self.open_config_location, width=112
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(8, 0),
        )
        ctk.CTkButton(
            buttons,
            text="校验并保存",
            command=self.save_config,
            width=120,
            fg_color=ACCENT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).grid(row=0, column=3, sticky="e")
        self._update_config_path()

    def _build_logs_page(self) -> None:
        page = self.page_frames["logs"]
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
        ctk.CTkLabel(
            toolbar,
            text="当前任务",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
        ).grid(row=0, column=0, padx=(16, 10), pady=12)
        self.log_task_box = ctk.CTkComboBox(
            toolbar,
            variable=self.log_task_value,
            values=["暂无任务"],
            command=lambda _value: self.refresh_log(),
            state="readonly",
            height=34,
            corner_radius=9,
            fg_color=SURFACE_ALT,
            border_color=BORDER,
            button_color=ACCENT,
            button_hover_color=ACCENT,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        )
        self.log_task_box.grid(row=0, column=1, sticky="ew", pady=12)
        action_button(toolbar, "刷新日志", self.refresh_log, width=96).grid(
            row=0, column=2, padx=(12, 0), pady=10
        )
        action_button(toolbar, "打开日志目录", self.open_log_location, width=112).grid(
            row=0,
            column=3,
            padx=14,
            pady=10,
        )

        log_frame = ctk.CTkFrame(
            page,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.log_text = ctk.CTkTextbox(
            log_frame,
            wrap="none",
            state="disabled",
            corner_radius=11,
            border_width=0,
            fg_color=SURFACE_ALT,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=9, pady=9)

    def show_page(self, key: str) -> None:
        if key not in self.page_frames:
            return
        self._active_page = key
        self.page_frames[key].tkraise()
        title, subtitle = PAGE_META[key]
        self.page_title.configure(text=title)
        self.page_subtitle.configure(text=subtitle)
        for name, button in self.nav_buttons.items():
            active = name == key
            button.configure(
                fg_color=ACCENT if active else "transparent",
                text_color="#FFFFFF" if active else TEXT,
            )
        if key == "logs":
            self.refresh_log()
        elif key == "processes":
            self.refresh_processes()

    def _change_appearance(self, label: str) -> None:
        modes = {"跟随系统": "System", "浅色": "Light", "深色": "Dark"}
        ctk.set_appearance_mode(modes[label])
        self.root.after(60, self._apply_tree_theme)
        self._set_status(f"界面已切换为{label}")

    def _apply_tree_theme(self) -> None:
        apply_table_style(self.root)
        for table in self._tables:
            apply_status_tags(table.tree)

    def _selected_task_id(self) -> str | None:
        return self.task_table.selected_id()

    def _selection_changed(self) -> None:
        task_id = self._selected_task_id()
        if not task_id:
            self.selected_task_value.set("尚未选择任务")
            return
        values = self.task_table.tree.item(task_id, "values")
        name = values[1] if len(values) > 1 else task_id
        self.selected_task_value.set(f"已选择：{name}  ·  {task_id}")
        self.log_task_value.set(task_id)

    def _open_overview_task(self) -> None:
        task_id = self.overview_table.selected_id()
        if not task_id:
            return
        self.show_page("tasks")
        if self.task_table.tree.exists(task_id):
            self.task_table.tree.selection_set(task_id)
            self.task_table.tree.focus(task_id)
            self.task_table.tree.see(task_id)
            self._selection_changed()

    def _require_task(self) -> str | None:
        task_id = self._selected_task_id()
        if task_id:
            return task_id
        self._set_status("请先从任务列表选择一个任务", "warning")
        return None

    def create_task(self) -> None:
        dialog = NewTaskDialog(self.root)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        name, preset = dialog.result
        try:
            task = self.service.create_task(name, preset)
        except Exception as exc:
            messagebox.showerror("创建失败", str(exc), parent=self.root)
            return
        self.show_page("tasks")
        self.refresh_all(select=task["id"])
        if preset == "manual":
            self.edit_task(task["id"])
        else:
            self._async_action(
                "自动启动任务", lambda: self.service.start_task(task["id"])
            )

    def edit_task(self, task_id: str | None = None) -> None:
        target = task_id or self._require_task()
        if not target:
            return
        YamlEditorDialog(
            self.root,
            f"编辑任务 YAML · {target}",
            lambda: self.service.store.read_text(target),
            lambda text: self.service.store.save_text(target, text),
            self.refresh_all,
        )

    def start_task(self) -> None:
        task_id = self._require_task()
        if task_id:
            self._async_action("启动任务", lambda: self.service.start_task(task_id))

    def control_task(self, action: str) -> None:
        task_id = self._require_task()
        if not task_id:
            return
        if action == "stop" and not messagebox.askyesno(
            "确认强制停止",
            "这会立即终止任务的全部受控子进程，是否继续？",
            parent=self.root,
        ):
            return
        labels = {
            "stop": "强制停止任务",
            "finish_now": "发送立即收尾指令",
            "finish_after_current": "发送批次后收尾指令",
        }
        self._async_action(
            labels[action],
            lambda: self.service.request(task_id, action),
        )

    def restart_task(self) -> None:
        task_id = self._require_task()
        if task_id:
            self._async_action("重启任务", lambda: self.service.restart_task(task_id))

    def delete_task(self) -> None:
        task_id = self._require_task()
        if not task_id:
            return
        answer = messagebox.askyesnocancel(
            "删除任务",
            "选择“是”会同时删除日志和运行状态；选择“否”只删除任务 YAML。",
            parent=self.root,
        )
        if answer is None:
            return
        try:
            self.service.delete_task(task_id, purge_runtime=answer)
            self.refresh_all()
            self._set_status("任务已删除")
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.root)

    def stop_process(self) -> None:
        selected = self.process_table.tree.selection()
        if not selected:
            self._set_status("请先从进程列表选择一个进程", "warning")
            return
        values = self.process_table.tree.item(selected[0], "values")
        pid = int(values[2])
        if not messagebox.askyesno(
            "确认终止",
            f"确认终止受控进程 PID {pid}？",
            parent=self.root,
        ):
            return
        self._async_action("终止进程", lambda: self.service.stop_process(pid))

    def refresh_all(self, select: str | None = None) -> None:
        try:
            items = self.service.list_tasks()
            processes = self.service.list_processes()
        except Exception as exc:
            self._set_status(f"刷新失败：{exc}", "error")
            return

        old_selection = select or self._selected_task_id()
        self.task_table.clear()
        self.overview_table.clear()
        self._task_ids = []
        for item in items:
            task = item["task"]
            state = item["state"]
            task_id = task["id"]
            status = str(state.get("status", "idle"))
            tag = (status,) if status in STATUS_TEXT else ()
            self._task_ids.append(task_id)
            common_values = (
                task.get("name", ""),
                task.get("preset", ""),
                STATUS_TEXT.get(status, status),
                state.get("phase", ""),
                state.get("runner_pid") or "",
                compact_timestamp(state.get("started_at")),
            )
            overview_values = (
                *common_values[:4],
                task_progress_label(task, state),
                *common_values[4:],
            )
            self.task_table.tree.insert(
                "",
                tk.END,
                iid=task_id,
                values=(task_id, *common_values),
                tags=tag,
            )
            self.overview_table.tree.insert(
                "",
                tk.END,
                iid=task_id,
                values=overview_values,
                tags=tag,
            )

        if old_selection and self.task_table.tree.exists(old_selection):
            self.task_table.tree.selection_set(old_selection)
            self.task_table.tree.focus(old_selection)
            self.task_table.tree.see(old_selection)
            self._selection_changed()
        elif not items:
            self.selected_task_value.set("尚未创建任务")
        else:
            self.selected_task_value.set("尚未选择任务")

        self._populate_processes(processes)
        self._update_summary(items, processes)
        self._update_log_choices()
        stamp = datetime.now().strftime("%H:%M:%S")
        self._set_status(f"已刷新 · {len(items)} 个任务 · {stamp}")

    def refresh_processes(self) -> None:
        try:
            processes = self.service.list_processes()
        except Exception as exc:
            self._set_status(f"进程刷新失败：{exc}", "error")
            return
        self._populate_processes(processes)
        self.summary_cards["processes"].set_value(len(processes))
        self._set_status(f"进程列表已刷新 · {len(processes)} 个受控进程")

    def _populate_processes(self, processes: list[dict[str, Any]]) -> None:
        self.process_table.clear()
        for index, process in enumerate(processes):
            status = str(process.get("status", ""))
            self.process_table.tree.insert(
                "",
                tk.END,
                iid=f"process-{index}-{process['pid']}",
                values=(
                    process.get("task_name") or process["task_id"],
                    ROLE_TEXT.get(
                        str(process.get("role", "")), process.get("role", "")
                    ),
                    process["pid"],
                    STATUS_TEXT.get(status, status),
                    compact_timestamp(process.get("started_at")),
                    process.get("command") or "",
                ),
                tags=(status,) if status in STATUS_TEXT else (),
            )

    def _update_summary(
        self,
        items: list[dict[str, Any]],
        processes: list[dict[str, Any]],
    ) -> None:
        active = sum(
            1 for item in items if item["state"].get("status") in ACTIVE_STATUSES
        )
        failed = sum(1 for item in items if item["state"].get("status") == "failed")
        self.summary_cards["total"].set_value(len(items))
        self.summary_cards["active"].set_value(active)
        self.summary_cards["failed"].set_value(failed)
        self.summary_cards["processes"].set_value(len(processes))

    def _update_log_choices(self) -> None:
        choices = self._task_ids or ["暂无任务"]
        self.log_task_box.configure(values=choices)
        current = self.log_task_value.get()
        if current not in self._task_ids:
            self.log_task_value.set(self._task_ids[0] if self._task_ids else "")
            self.log_task_box.set(self._task_ids[0] if self._task_ids else "暂无任务")

    def _config_selected(self, label: str) -> None:
        self._config_drafts[self._current_config_kind] = self.config_text.get(
            "1.0", "end-1c"
        )
        self._current_config_kind = "project" if label == "项目配置" else "webhook"
        if self._current_config_kind not in self._config_drafts:
            try:
                self._config_drafts[self._current_config_kind] = (
                    self.service.config_manager.read_text(self._current_config_kind)
                )
            except Exception as exc:
                messagebox.showerror("读取配置失败", str(exc), parent=self.root)
                return
        self._replace_config_text(self._config_drafts[self._current_config_kind])
        self._update_config_path()

    def reload_config(
        self,
        kind: str | None = None,
        *,
        quiet: bool = False,
    ) -> None:
        target = kind or self._current_config_kind
        try:
            self.service.reload()
            content = self.service.config_manager.read_text(target)
        except Exception as exc:
            if not quiet:
                messagebox.showerror("读取配置失败", str(exc), parent=self.root)
            return
        self._config_drafts[target] = content
        if target == self._current_config_kind:
            self._replace_config_text(content)
            self._update_config_path()
        if not quiet:
            self._set_status("已从磁盘重新读取配置")

    def _replace_config_text(self, content: str) -> None:
        self.config_text.delete("1.0", tk.END)
        self.config_text.insert("1.0", content)

    def save_config(self) -> None:
        kind = self._current_config_kind
        content = self.config_text.get("1.0", "end-1c")
        try:
            self.service.config_manager.save_text(kind, content)
            self.service.reload()
        except Exception as exc:
            messagebox.showerror("配置保存失败", str(exc), parent=self.root)
            return
        self._config_drafts[kind] = content
        self.refresh_all()
        self._set_status("YAML 已校验并写入磁盘")
        messagebox.showinfo(
            "配置已保存",
            "YAML 已通过校验并写入磁盘。",
            parent=self.root,
        )

    def _current_config_path(self) -> Path:
        if self._current_config_kind == "project":
            return self.service.paths.config_file
        return self.service.paths.webhook_file

    def _update_config_path(self) -> None:
        self.config_path_label.configure(text=str(self._current_config_path()))

    def open_config_location(self) -> None:
        self._open_path(self._current_config_path().parent)

    def open_log_location(self) -> None:
        task_id = self.log_task_value.get()
        path = (
            self.service.store.log_path(task_id).parent
            if task_id in self._task_ids
            else self.service.store.task_runtime_dir
        )
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("无法打开路径", str(exc))

    def refresh_log(self) -> None:
        task_id = self.log_task_value.get()
        if task_id not in self._task_ids:
            content = "尚未选择任务。\n"
        else:
            path = self.service.store.log_path(task_id)
            try:
                if path.exists():
                    size = path.stat().st_size
                    with path.open("rb") as handle:
                        handle.seek(max(0, size - 250_000))
                        content = handle.read().decode("utf-8", errors="replace")
                else:
                    content = "日志尚未生成。\n"
            except OSError as exc:
                content = f"读取日志失败：{exc}\n"
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", content)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _async_action(self, label: str, operation: Callable[[], object]) -> None:
        if self._busy:
            self._set_status("已有管理操作正在执行，请稍候", "warning")
            return
        self._busy += 1
        self.refresh_button.configure(state="disabled")
        self._set_status(f"{label}中…", "busy")

        def work() -> None:
            try:
                operation()
            except Exception as exc:
                self.root.after(
                    0,
                    lambda error=exc: self._action_finished(label, error),
                )
            else:
                self.root.after(0, lambda: self._action_finished(label, None))

        threading.Thread(target=work, name=f"gui-{label}", daemon=True).start()

    def _action_finished(self, label: str, error: Exception | None) -> None:
        self._busy = max(0, self._busy - 1)
        self.refresh_button.configure(state="normal")
        if error:
            messagebox.showerror(f"{label}失败", str(error), parent=self.root)
        self.refresh_all()
        self._set_status(
            f"{label}{'失败' if error else '完成'}",
            "error" if error else "success",
        )

    def _set_status(self, message: str, kind: str = "success") -> None:
        colors = {
            "success": SUCCESS,
            "warning": WARNING,
            "error": DANGER,
            "busy": ACCENT,
        }
        self.status_value.set(message)
        self.status_dot.configure(text_color=colors.get(kind, SUCCESS))

    def _periodic_refresh(self) -> None:
        if self._closed:
            return
        if self._busy == 0:
            self.refresh_all()
            if self._active_page == "logs":
                self.refresh_log()
        self.root.after(self.REFRESH_MS, self._periodic_refresh)

    def close(self) -> None:
        self._closed = True
        self.root.destroy()
