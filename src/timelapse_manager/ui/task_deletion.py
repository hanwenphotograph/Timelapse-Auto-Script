"""Batch deletion orchestration for the task management page."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class BatchDeletionResult:
    deleted: tuple[str, ...]
    failures: tuple[tuple[str, str], ...]


def delete_tasks(
    task_ids: Iterable[str],
    operation: Callable[[str], None],
) -> BatchDeletionResult:
    """Delete every unique task and retain per-task failures for the GUI."""
    deleted: list[str] = []
    failures: list[tuple[str, str]] = []
    for task_id in dict.fromkeys(task_ids):
        try:
            operation(task_id)
        except Exception as exc:
            failures.append((task_id, str(exc) or type(exc).__name__))
        else:
            deleted.append(task_id)
    return BatchDeletionResult(tuple(deleted), tuple(failures))
