"""Cross-platform eternal capture and serial background processing."""

from __future__ import annotations

import os
import queue
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from timelapse_manager.errors import ConfigError, TaskError
from timelapse_manager.io_utils import (
    load_json,
    load_yaml,
    now_iso,
    save_json,
    save_yaml,
)
from timelapse_manager.maintenance import check_disk_space, cleanup_work_directory
from timelapse_manager.process_utils import process_identity, process_matches
from timelapse_manager.runtime import HardStopRequested, TaskRuntime


GROUP_PATTERN = re.compile(r"^(\d+)_")


class EternalWorkflow:
    def __init__(self, runtime: TaskRuntime):
        self.runtime = runtime
        self.task = runtime.task
        task_options = self.task["eternal"]
        project_options = runtime.project["eternal"]
        self.batch_groups = int(
            task_options.get("batch_groups") or project_options["batch_groups"]
        )
        self.images_per_group = int(
            task_options.get("images_per_group") or project_options["images_per_group"]
        )
        self.archive_retry_seconds = float(project_options["archive_retry_seconds"])
        state_value = task_options.get("state_dir")
        self.state_dir = (
            runtime.paths.resolve_from_root(str(state_value))
            if state_value
            else runtime.auto_root / ".eternal"
        )
        self.capture_dir = self.state_dir / "capture"
        self.queue_dir = self.state_dir / "queue"
        self.lock_dir = self.state_dir / "lock"
        self.pending_file = self.state_dir / "pending-python.yaml"
        self.counter_file = self.state_dir / "batch-counter"
        self._archive_lock = threading.RLock()
        self._pending: list[dict[str, Any]] = []
        self._known_groups: set[int] = set()
        self._current_group: int | None = None
        self._capture_seen = False
        self._batch_boundary = threading.Event()
        self._archive_queue: queue.Queue[Path] = queue.Queue()
        self._drain_archives = threading.Event()
        self._drain_queue = threading.Event()
        self._organizer: threading.Thread | None = None
        self._processor: threading.Thread | None = None
        self._processor_failures: list[str] = []
        self._batches_dispatched = 0

    def run(self) -> None:
        initialized = False
        try:
            self._initialize()
            initialized = True
            self.runtime.set_phase(
                "永续拍摄初始化",
                f"每 {self.batch_groups} 组归档，暂存目录 {self.capture_dir}",
            )
            self.runtime.notify(
                "runner_started",
                f"永续 Timelapse 已启动，每 {self.batch_groups} 组进入后台处理队列",
            )
            self._organizer = threading.Thread(
                target=self._archive_loop,
                name=f"eternal-archive-{self.task['id']}",
                daemon=True,
            )
            self._organizer.start()
            self._processor = threading.Thread(
                target=self._processing_loop,
                name=f"eternal-processor-{self.task['id']}",
                daemon=True,
            )
            self._processor.start()
            self._camera_loop()
            self._finish_gracefully()
        finally:
            self._drain_archives.set()
            if self._organizer:
                self._organizer.join(timeout=5)
            self._drain_queue.set()
            if self._processor:
                self._processor.join(timeout=5)
            if initialized or self.lock_dir.exists():
                self._release_lock()

    def _initialize(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._acquire_lock()
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        if not self.counter_file.exists():
            self.counter_file.write_text("0\n", encoding="ascii")
        self._load_pending()
        self._recover_archives()
        for failed in sorted(self.queue_dir.glob("*.failed.yaml")):
            ready = failed.with_name(failed.name.replace(".failed.yaml", ".ready.yaml"))
            failed.replace(ready)
        self._sync_complete_groups()

    def _acquire_lock(self) -> None:
        owner_path = self.lock_dir / "owner.json"
        legacy_pid_path = self.lock_dir / "pid"
        try:
            self.lock_dir.mkdir()
        except FileExistsError:
            owner = load_json(owner_path, {})
            pid = owner.get("pid") if isinstance(owner, dict) else None
            created = owner.get("created_at") if isinstance(owner, dict) else None
            if not pid and legacy_pid_path.exists():
                try:
                    pid = int(legacy_pid_path.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    pid = None
            if process_matches(pid, created):
                raise TaskError(f"永续 Timelapse 已在运行，PID={pid}")
            for entry in self.lock_dir.iterdir():
                if entry.is_file() or entry.is_symlink():
                    entry.unlink(missing_ok=True)
            try:
                self.lock_dir.rmdir()
                self.lock_dir.mkdir()
            except OSError as exc:
                raise TaskError(f"无法清理永续任务状态锁: {self.lock_dir}") from exc
        save_json(
            owner_path,
            {
                "pid": os.getpid(),
                "created_at": process_identity(os.getpid()),
                "task_id": self.task["id"],
            },
        )

    def _release_lock(self) -> None:
        owner_path = self.lock_dir / "owner.json"
        owner = load_json(owner_path, {})
        if not isinstance(owner, dict) or owner.get("pid") != os.getpid():
            return
        for entry in self.lock_dir.iterdir():
            if entry.is_file() or entry.is_symlink():
                entry.unlink(missing_ok=True)
        try:
            self.lock_dir.rmdir()
        except OSError:
            pass

    def _load_pending(self) -> None:
        if self.pending_file.exists():
            value = load_yaml(self.pending_file)
            pending = value.get("groups", [])
            if isinstance(pending, list):
                self._pending = [
                    item
                    for item in pending
                    if isinstance(item, dict) and "group" in item
                ]
        self._known_groups = {int(item["group"]) for item in self._pending}

    def _save_pending(self) -> None:
        save_yaml(self.pending_file, {"groups": self._pending})

    def _group_files(self, group: int) -> list[Path]:
        prefix = f"{group:04d}_"
        return sorted(
            path for path in self.capture_dir.glob(f"{prefix}*") if path.is_file()
        )

    def _sync_complete_groups(self) -> None:
        groups: dict[int, list[Path]] = {}
        for path in self.capture_dir.iterdir():
            if not path.is_file():
                continue
            match = GROUP_PATTERN.match(path.name)
            if match:
                groups.setdefault(int(match.group(1)), []).append(path)
        for group, files in sorted(groups.items()):
            if len(files) >= self.images_per_group:
                self._record_complete_group(group)

    def _record_complete_group(self, group: int) -> None:
        with self._archive_lock:
            if group in self._known_groups:
                return
            files = self._group_files(group)
            if len(files) < self.images_per_group:
                return
            completed = max(path.stat().st_mtime for path in files)
            self._pending.append({"group": group, "completed_at": completed})
            self._known_groups.add(group)
            self._save_pending()
            self.runtime.set_progress(
                eternal_pending_groups=len(self._pending),
                eternal_last_group=group,
                eternal_batches=self._batches_dispatched,
            )
            while len(self._pending) >= self.batch_groups:
                self._dispatch_batch(self.batch_groups, full_batch=True)

    def _next_sequence(self) -> int:
        try:
            current = int(self.counter_file.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            current = 0
        sequence = current + 1
        self.counter_file.write_text(f"{sequence}\n", encoding="ascii")
        return sequence

    def _create_batch_directory(self, start_epoch: float, end_epoch: float) -> Path:
        start = datetime.fromtimestamp(start_epoch).astimezone()
        end = datetime.fromtimestamp(end_epoch).astimezone()
        parent = self.runtime.auto_root / start.strftime("%Y-%m-%d")
        parent.mkdir(parents=True, exist_ok=True)
        stem = f"{start:%H%M}-{end:%H%M}"
        candidate = parent / stem
        suffix = 1
        while True:
            try:
                candidate.mkdir()
                return candidate
            except FileExistsError:
                suffix += 1
                candidate = parent / f"{stem}-{suffix}"

    def _dispatch_batch(self, count: int, *, full_batch: bool) -> None:
        selected = list(self._pending[:count])
        if not selected:
            return
        all_files = [
            path for item in selected for path in self._group_files(int(item["group"]))
        ]
        if not all_files:
            selected_groups = {int(item["group"]) for item in selected}
            self._pending = [
                item
                for item in self._pending
                if int(item["group"]) not in selected_groups
            ]
            self._known_groups -= selected_groups
            self._save_pending()
            return
        start_epoch = min(path.stat().st_mtime for path in all_files)
        end_epoch = max(path.stat().st_mtime for path in all_files)
        sequence = self._next_sequence()
        batch_dir = self._create_batch_directory(start_epoch, end_epoch)
        manifest = self.state_dir / f"archive.{sequence:08d}.yaml"
        manifest_data = {
            "sequence": sequence,
            "batch_dir": str(batch_dir),
            "groups": selected,
            "files": [str(path) for path in all_files],
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
        }
        save_yaml(manifest, manifest_data)
        selected_groups = {int(item["group"]) for item in selected}
        self._pending = [
            item for item in self._pending if int(item["group"]) not in selected_groups
        ]
        self._save_pending()
        self._archive_queue.put(manifest)
        self._batches_dispatched += 1
        self.runtime.set_progress(
            eternal_pending_groups=len(self._pending),
            eternal_batches=self._batches_dispatched,
            eternal_archives=self._archive_queue.qsize(),
            eternal_queue=self._ready_count(),
        )
        if full_batch and self.runtime.finish_after_current.is_set():
            self._batch_boundary.set()

    def _complete_archive(self, manifest: Path, data: dict[str, Any]) -> None:
        sequence = int(data["sequence"])
        batch_dir = Path(str(data["batch_dir"]))
        batch_dir.mkdir(parents=True, exist_ok=True)
        groups = [int(item["group"]) for item in data["groups"]]
        source_files = [Path(str(value)) for value in data.get("files", [])]
        if not source_files:
            source_files = [
                path for group in groups for path in self._group_files(group)
            ]
        for image in source_files:
            destination = batch_dir / image.name
            if destination.exists():
                continue
            if not image.is_file():
                raise TaskError(f"归档源图片缺失: {image}")
            shutil.move(str(image), str(destination))
        start = datetime.fromtimestamp(float(data["start_epoch"])).astimezone()
        end = datetime.fromtimestamp(float(data["end_epoch"])).astimezone()
        (batch_dir / ".eternal-batch.tsv").write_text(
            f"{start:%Y-%m-%d}\t{start:%H:%M}\t{end:%H:%M}\n", encoding="utf-8"
        )
        marker = self.queue_dir / f"{sequence:08d}.ready.yaml"
        save_yaml(
            marker,
            {
                "sequence": sequence,
                "batch_dir": str(batch_dir),
                "work_date": start.strftime("%Y-%m-%d"),
                "start_at": start.strftime("%H:%M"),
                "end_at": end.strftime("%H:%M"),
                "queued_at": now_iso(),
            },
        )
        with self._archive_lock:
            group_set = set(groups)
            self._pending = [
                item for item in self._pending if int(item["group"]) not in group_set
            ]
            self._known_groups -= group_set
            self._save_pending()
        manifest.unlink(missing_ok=True)
        image_count = sum(
            1
            for path in batch_dir.iterdir()
            if path.is_file() and not path.name.startswith(".")
        )
        self.runtime.log(
            f"永续批次 {sequence} 已进入处理队列，组数={len(groups)}，图片={image_count}，目录={batch_dir}"
        )
        self.runtime.notify_async(
            "eternal_batch_queued",
            f"永续批次 {sequence} 已归档并进入处理队列，目录 {batch_dir}",
        )

    def _recover_archives(self) -> None:
        for manifest in sorted(self.state_dir.glob("archive.*.yaml")):
            try:
                data = load_yaml(manifest)
                self._known_groups.update(
                    int(item["group"]) for item in data.get("groups", [])
                )
            except (OSError, KeyError, TypeError, ValueError, ConfigError) as exc:
                raise TaskError(f"无法读取永续归档清单 {manifest}: {exc}") from exc
            self._archive_queue.put(manifest)
            self.runtime.log(f"已重新排队未完成归档: {manifest.name}")

    def _archive_loop(self) -> None:
        self.runtime.log("永续归档线程已启动")
        while True:
            if self.runtime.hard_stop.is_set():
                return
            try:
                manifest = self._archive_queue.get(timeout=0.25)
            except queue.Empty:
                if self._drain_archives.is_set():
                    return
                continue
            try:
                while manifest.exists() and not self.runtime.hard_stop.is_set():
                    try:
                        self._complete_archive(manifest, load_yaml(manifest))
                        break
                    except (
                        OSError,
                        KeyError,
                        ValueError,
                        ConfigError,
                        TaskError,
                    ) as exc:
                        self.runtime.log(
                            f"永续归档 {manifest.name} 失败: {exc}，{self.archive_retry_seconds:g} 秒后重试"
                        )
                        deadline = time.monotonic() + self.archive_retry_seconds
                        while time.monotonic() < deadline:
                            if self.runtime.hard_stop.is_set():
                                return
                            time.sleep(min(0.25, deadline - time.monotonic()))
            finally:
                self._archive_queue.task_done()

    def _camera_output_handler(self, line: str) -> None:
        match = re.search(r"Starting\s+capture\s+round\s+(\d+)", line)
        if match:
            group = int(match.group(1))
            previous = self._current_group
            self._current_group = group
            if previous is not None and previous != group:
                self._record_complete_group(previous)
            if not self._capture_seen:
                self._capture_seen = True
                self.runtime.set_phase("永续拍摄中", str(self.capture_dir))
                self.runtime.notify_async(
                    "entered_key_node",
                    f"永续 camera-timelapse 真正开始拍摄，目录 {self.capture_dir}",
                )
        if (
            "Deleting " in line
            and " from camera" in line
            and self._current_group is not None
        ):
            self._record_complete_group(self._current_group)

    def _camera_loop(self) -> None:
        interval = self.task["capture"].get("interval_seconds")
        if interval is None:
            interval = self.runtime.project["capture_interval_seconds"]
        retry_delay = self.task["retry"].get("delay_seconds")
        if retry_delay is None:
            retry_delay = self.runtime.project["runtime"]["retry_delay_seconds"]
        while True:
            camera = self.runtime.spawn(
                "camera-timelapse-eternal",
                self.runtime.camera_command
                + [str(self.capture_dir), "--interval", str(interval)],
                cwd=self.capture_dir,
                extra_env={"PYTHONUNBUFFERED": "1"},
                on_line=self._camera_output_handler,
            )
            self.runtime.notify_async(
                "camera_process_started",
                f"永续 camera-timelapse 已启动，间隔 {interval} 秒，目录 {self.capture_dir}",
            )
            graceful = False
            while True:
                self.runtime.poll_controls()
                if self.runtime.hard_stop.is_set():
                    camera.terminate()
                    raise HardStopRequested
                if self.runtime.finish_now.is_set() or self._batch_boundary.is_set():
                    graceful = True
                    self.runtime.set_phase("永续拍摄收尾", "正在停止相机并排空处理队列")
                    camera.terminate()
                code = camera.poll()
                if code is not None:
                    break
                time.sleep(self.runtime.poll_interval)
            if graceful:
                return
            self.runtime.log(
                f"永续相机进程意外结束，退出码={code}，{retry_delay:g} 秒后重启"
            )
            self.runtime.notify_async(
                "eternal_camera_restarting",
                f"永续相机进程意外结束，退出码 {code}，将在 {retry_delay:g} 秒后重启",
            )
            deadline = time.monotonic() + float(retry_delay)
            while time.monotonic() < deadline:
                self.runtime.poll_controls()
                if self.runtime.hard_stop.is_set():
                    raise HardStopRequested
                if self.runtime.finish_now.is_set():
                    return
                time.sleep(min(self.runtime.poll_interval, deadline - time.monotonic()))

    def _ready_count(self) -> int:
        return sum(1 for _ in self.queue_dir.glob("*.ready.yaml"))

    def _processing_loop(self) -> None:
        self.runtime.log("永续后台串行处理线程已启动")
        while True:
            if self.runtime.hard_stop.is_set():
                return
            markers = sorted(self.queue_dir.glob("*.ready.yaml"))
            if not markers:
                if self._drain_queue.is_set():
                    return
                time.sleep(float(self.runtime.project["eternal"]["queue_poll_seconds"]))
                continue
            marker = markers[0]
            try:
                data = load_yaml(marker)
                success = self._process_batch(marker, data)
            except Exception as exc:
                success = False
                self.runtime.log(f"永续批次标记处理失败 {marker}: {exc}")
            if self.runtime.hard_stop.is_set():
                return
            if success:
                marker.unlink(missing_ok=True)
            else:
                failed = marker.with_name(
                    marker.name.replace(".ready.yaml", ".failed.yaml")
                )
                try:
                    marker.replace(failed)
                except OSError:
                    pass
                self._processor_failures.append(marker.name)

    def _bracket_output_handler(self, batch_dir: Path):
        def handle(line: str) -> None:
            if "Fusing " in line:
                self.runtime.set_phase("永续批次 HDR 融合", str(batch_dir))
            elif "Deflickering fused frames." in line:
                self.runtime.set_phase("永续批次去闪", str(batch_dir))
            elif "Creating video from " in line:
                self.runtime.set_phase("永续批次视频导出", str(batch_dir))

        return handle

    def _process_batch(self, marker: Path, data: dict[str, Any]) -> bool:
        sequence = int(data["sequence"])
        batch_dir = Path(str(data["batch_dir"]))
        self.runtime.set_phase("永续批次后期处理", f"批次 {sequence}，目录 {batch_dir}")
        if not self.task["processing"].get("enabled", True):
            self.runtime.log(f"永续批次 {sequence} 已归档，任务配置为不执行后期处理")
            return True
        self.runtime.notify_async(
            "entered_key_node",
            f"永续批次 {sequence} 开始 Bracketlapse 处理，目录 {batch_dir}",
        )
        env = {
            "BRACKLAPSE_RUN_DATE": str(data["work_date"]),
            "BRACKLAPSE_RUN_START_AT": str(data["start_at"]),
            "BRACKLAPSE_RUN_END_AT": str(data["end_at"]),
        }
        child = self.runtime.spawn(
            f"bracketlapse-batch-{sequence}",
            self.runtime.bracket_command + [str(batch_dir), "--merge-subdirs"],
            cwd=batch_dir,
            extra_env=env,
            on_line=self._bracket_output_handler(batch_dir),
        )
        while child.poll() is None:
            if self.runtime.hard_stop.is_set():
                child.terminate()
                return False
            time.sleep(self.runtime.poll_interval)
        code = child.poll()
        if code != 0:
            self.runtime.log(f"永续批次 {sequence} 处理失败，退出码={code}")
            return False
        self.runtime.webhook.notify_image(
            "webhook-image",
            f"图片推送：永续批次 {sequence}，日期 {data['work_date']}，时间 {data['start_at']}-{data['end_at']}",
            batch_dir,
        )
        cleanup = self.task["cleanup"]
        if cleanup.get("enabled"):
            try:
                cleanup_work_directory(
                    batch_dir,
                    list(cleanup["keep_directories"]),
                    self.runtime.log,
                    protected_paths=[
                        self.runtime.paths.root,
                        self.runtime.auto_root,
                        self.state_dir,
                        self.capture_dir,
                    ],
                )
            except (OSError, TaskError) as exc:
                self.runtime.log(f"永续批次 {sequence} 清理失败: {exc}")
                return False
        threshold = float(self.runtime.project["disk_space_warning_threshold_gb"])
        remaining = check_disk_space(batch_dir, threshold, self.runtime.log)
        if threshold > 0 and remaining < threshold:
            self.runtime.notify_async(
                "disk_space_warning",
                f"磁盘剩余 {remaining:.2f}GB，低于阈值 {threshold:g}GB",
            )
        self.runtime.notify_async(
            "ended", f"永续批次 {sequence} 已完成处理、导出和清理，目录 {batch_dir}"
        )
        return True

    def _finish_gracefully(self) -> None:
        self.runtime.set_phase("整理最后批次", "正在归档剩余完整曝光组")
        if self._current_group is not None:
            self._record_complete_group(self._current_group)
        self._sync_complete_groups()
        with self._archive_lock:
            if self._pending:
                self._dispatch_batch(len(self._pending), full_batch=False)
        self._drain_archives.set()
        while self._organizer and self._organizer.is_alive():
            self.runtime.poll_controls()
            if self.runtime.hard_stop.is_set():
                raise HardStopRequested
            self.runtime.set_progress(eternal_archives=self._archive_queue.qsize())
            self._organizer.join(timeout=self.runtime.poll_interval)
        incomplete = [path for path in self.capture_dir.iterdir() if path.is_file()]
        if incomplete:
            if self.task["cleanup"].get("delete_incomplete_groups"):
                for path in incomplete:
                    path.unlink(missing_ok=True)
                self.runtime.log(
                    f"已删除未形成完整曝光组的图片，数量={len(incomplete)}"
                )
            else:
                self.runtime.log(
                    f"已保留未形成完整曝光组的图片，数量={len(incomplete)}"
                )
        self._drain_queue.set()
        while self._processor and self._processor.is_alive():
            self.runtime.poll_controls()
            if self.runtime.hard_stop.is_set():
                raise HardStopRequested
            self.runtime.set_progress(eternal_queue=self._ready_count())
            self._processor.join(timeout=self.runtime.poll_interval)
        if self._processor_failures or list(self.queue_dir.glob("*.failed.yaml")):
            raise TaskError("永续拍摄已停止，但存在处理失败的批次")
        self.runtime.notify_async("ended", "永续拍摄及所有后台批次已经完成并关闭")
