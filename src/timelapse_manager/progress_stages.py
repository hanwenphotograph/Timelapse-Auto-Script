"""Persisted finite-task and child progress stage names."""

from __future__ import annotations


MAIN_STAGES = (
    "waiting_capture",
    "capture",
    "waiting_processing",
    "video_processing",
)
CHILD_STAGES = ("hdr", "sunset", "video")


def validate_main_stage(stage: str) -> None:
    if stage not in MAIN_STAGES:
        raise ValueError(f"无效的主进度阶段: {stage}")


def validate_child_stage(stage: str | None) -> None:
    if stage is not None and stage not in CHILD_STAGES:
        raise ValueError(f"无效的子进度阶段: {stage}")
