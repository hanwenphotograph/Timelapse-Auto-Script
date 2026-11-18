"""Persist finite captures as independently controllable processing tasks."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from timelapse_manager.album_naming import date_album_path
from timelapse_manager.errors import TaskError
from timelapse_manager.io_utils import now_iso
from timelapse_manager.processing.schedule import processing_due_at
from timelapse_manager.workflows.scheduled_finish import ScheduledFinisher
from timelapse_manager.workflows.scheduled_processing import ScheduledProcessing
from timelapse_manager.workflows.scheduled_support import CaptureProgress, WorkSpec


def enqueue_capture(runtime, spec, progress, preserve_names) -> str:
    from timelapse_manager.processing.scheduler import ensure_scheduler
    from timelapse_manager.service import ManagerService

    # A deterministic ID makes retrying an interrupted enqueue idempotent.
    run_key = f"{runtime.task_id}:{runtime.state.get('started_at')}"
    task_id = f"process-{runtime.task_id[:32]}-{sha256(run_key.encode()).hexdigest()[:12]}"
    store = runtime.store
    ready_at = now_iso()
    if not store.definition_path(task_id).exists():
        task = deepcopy(runtime.task)
        task.update(
            id=task_id,
            name=f"后期处理 · {task['name']}",
            preset="processing",
            created_at=ready_at,
        )
        task.pop("continuation", None)
        task["retry"] = {"enabled": False}
        task["deferred_processing"] = {
            "source_task_id": runtime.task_id,
            "ready_at": ready_at,
            "spec": {**asdict(spec), "work_dir": str(spec.work_dir)},
            "rounds": progress.rounds,
            "capture_started": progress.started,
            "preserve_names": sorted(preserve_names),
        }
        store.add_definition(task)
        state = store.default_state(task_id)
        state.update(phase="等待定时处理", message="照片已下载，等待每天配置的处理时间")
        store.write_state(task_id, state)
    due = processing_due_at(runtime.project, ready_at)
    runtime.set_main_stage("waiting_processing")
    runtime.set_progress(processing_task_id=task_id, processing_due_at=due.isoformat())
    runtime.set_phase(
        "照片下载完成，已加入处理队列", f"{due:%Y-%m-%d %H:%M} · {task_id}"
    )
    runtime.notify_async(
        "processing_queued",
        f"照片已下载，计划 {due:%Y-%m-%d %H:%M} 处理，目录 {spec.work_dir}",
    )
    ensure_scheduler(ManagerService(runtime.paths.root, start_scheduler=False))
    return task_id


def processing_work_dir(path: Path, auto_root: Path) -> Path:
    if path.is_dir():
        return path
    # Earlier jobs may have added a sunset score to the shared date container.
    try:
        relative = path.relative_to(auto_root)
    except ValueError:
        return path
    if len(relative.parts) == 2:
        date_name = relative.parts[0].split("-S")[0]
        candidate = date_album_path(auto_root, date_name) / relative.parts[1]
        if candidate.is_dir():
            return candidate
    return path


def run_processing(runtime) -> None:
    data = runtime.task["deferred_processing"]
    raw_spec = dict(data["spec"])
    raw_spec["work_dir"] = processing_work_dir(
        Path(raw_spec["work_dir"]), runtime.auto_root
    )
    spec = WorkSpec(**raw_spec)
    if not spec.work_dir.is_dir():
        raise TaskError(f"待处理素材目录不存在，已保留队列记录: {spec.work_dir}")
    runtime.set_main_stage("waiting_processing")
    runtime.set_phase("开始集中处理照片", str(spec.work_dir))
    score_session = runtime.sunset_score.start_stream(spec.work_dir, spec.score_label)
    progress = CaptureProgress(started=data["capture_started"], rounds=data["rounds"])
    processing = ScheduledProcessing(
        runtime,
        spec,
        progress,
        score_session.scan if score_session else None,
        {
            "BRACKLAPSE_RUN_DATE": spec.start_date,
            "BRACKLAPSE_RUN_START_AT": spec.start_at,
            "BRACKLAPSE_RUN_END_AT": spec.end_at,
        },
    )
    success = processing.run_batch()
    success = ScheduledFinisher(runtime).finish(
        spec,
        success,
        score_session,
        capture_started=progress.started,
        preserve_names=frozenset(data["preserve_names"]),
    )
    if not success:
        raise TaskError(
            "集中处理失败，原始照片已保留，请查看任务日志后重新启动处理任务"
        )
