"""Reusable task table widget."""

from __future__ import annotations

from collections.abc import Iterable
from tkinter import ttk

import customtkinter as ctk

from timelapse_manager.ui.theme import ACCENT, BORDER, SURFACE


def responsive_column_widths(
    columns: Iterable[str], widths: dict[str, int], available_width: int
) -> dict[str, int]:
    """Distribute table width without allowing a horizontal overflow."""
    names = tuple(columns)
    if not names:
        return {}
    preferred = {name: max(1, int(widths[name])) for name in names}
    available = max(0, int(available_width))
    minimum = {name: min(56, preferred[name]) for name in names}
    minimum_total = sum(minimum.values())
    if available < minimum_total:
        return _proportional_widths(names, preferred, available)
    extra = _proportional_widths(
        names,
        {name: max(1, preferred[name] - minimum[name]) for name in names},
        available - minimum_total,
    )
    return {name: minimum[name] + extra[name] for name in names}


def _proportional_widths(
    columns: tuple[str, ...], weights: dict[str, int], total: int
) -> dict[str, int]:
    weight_total = sum(weights.values())
    if total <= 0 or weight_total <= 0:
        return {name: 0 for name in columns}
    values = {
        name: total * weights[name] // weight_total
        for name in columns
    }
    remainder = total - sum(values.values())
    order = sorted(
        columns,
        key=lambda name: (total * weights[name] % weight_total, name),
        reverse=True,
    )
    for name in order[:remainder]:
        values[name] += 1
    return values


class ModernTable(ctk.CTkFrame):
    """A rounded container around a ttk table with a vertical scrollbar."""

    def __init__(
        self,
        parent: object,
        columns: Iterable[str],
        headings: dict[str, str],
        widths: dict[str, int],
    ) -> None:
        super().__init__(
            parent,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._columns = tuple(columns)
        self._widths = dict(widths)
        self.tree = ttk.Treeview(
            self,
            columns=self._columns,
            show="headings",
            selectmode="browse",
            style="Modern.Treeview",
        )
        for column in self._columns:
            self.tree.heading(column, text=headings[column], anchor="center")
            self.tree.column(
                column,
                width=widths[column],
                minwidth=1,
                stretch=False,
                anchor="center",
            )

        vertical = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self.tree.yview,
            width=12,
            button_color=BORDER,
            button_hover_color=ACCENT,
        )
        self.tree.configure(
            yscrollcommand=vertical.set,
        )
        self.tree.bind("<Configure>", self._resize_columns, add="+")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=(1, 0))
        vertical.grid(row=0, column=1, sticky="ns", padx=(2, 4), pady=(8, 2))
        self.after_idle(self._resize_columns)

    def _resize_columns(self, _event: object | None = None) -> None:
        viewport_width = self.tree.winfo_width()
        if viewport_width <= 1:
            return
        target_widths = responsive_column_widths(
            self._columns, self._widths, viewport_width - 2
        )
        for column, width in target_widths.items():
            if int(self.tree.column(column, "width")) != width:
                self.tree.column(column, width=width)

    def clear(self) -> None:
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)

    def selected_id(self) -> str | None:
        selected = self.tree.selection()
        return selected[0] if selected else None
