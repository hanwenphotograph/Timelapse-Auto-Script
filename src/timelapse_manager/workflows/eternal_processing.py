"""Post-process one archived eternal-capture batch."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from timelapse_manager.bracketlapse import parse_hdr_ready
from timelapse_manager.errors import TaskError
from timelapse_manager.maintenance import check_disk_space, cleanup_work_directory
from timelapse_manager.runtime import TaskRuntime


class EternalBatchProcessor:
    def __init__(self, runtime: TaskRuntime, state_dir: Path, capture_dir: Path):
        self.runtime = runtime
        self.task = runtime.task
        self.state_dir = state_dir
        self.capture_dir = capture_dir

    def process(self, data: dict[str, Any]) -> bool:
        sequence = int(data["sequence"])
        batch_dir = Path(str(data["batch_dir"]))
        self.runtime.set_phase("永续批次后期处理", f"批次 {sequence}，目录 {batch_dir}")
        if not self.task["processing"].get("enabled", True):
            self.runtime.log(f"永续批次 {sequence} 已归档，任务配置为不执行后期处理")
            return True
        self.runtime.notify_async(
            "entered_key_node",
            f"永续批次 {sequence} 开始流水线处理，目录 {batch_dir}",
        )
        label = (
            f"永续批次 {sequence}，日期 {data['work_date']}，"
            f"时间 {data['start_at']}-{data['end_at']}"
        )
        env = self._environment(data)
        score_session = self.runtime.sunset_score.start_stream(batch_dir, label)
        if not self._run_bracket(sequence, batch_dir, env, score_session):
            return False
        score_decision = self._finish_score(sequence, batch_dir, label, score_session)
        if score_decision is False:
            return False
        if score_decision is None and not self.runtime.sunset_score.enabled:
            self.runtime.webhook.notify_image(
                "webhook-image", f"图片推送：{label}", batch_dir
            )
        if not self._cleanup(sequence, batch_dir, score_decision):
            return False
        self._check_disk(batch_dir)
        self.runtime.notify_async(
            "ended", f"永续批次 {sequence} 已完成处理、导出和清理，目录 {batch_dir}"
        )
        return True

    def _run_bracket(
        self, sequence: int, batch_dir: Path, env: dict[str, str], score_session
    ) -> bool:
        def handle(line: str) -> None:
            event = parse_hdr_ready(line, batch_dir)
            if event is not None and score_session is not None:
                score_session.scan()
            if "Fusing " in line:
                self.runtime.set_phase("永续批次 HDR 融合", str(batch_dir))
            elif "Deflickering fused frames." in line:
                self.runtime.set_phase("永续批次去闪", str(batch_dir))
            elif "Creating video from " in line:
                self.runtime.set_phase("永续批次视频导出", str(batch_dir))

        child = self.runtime.spawn(
            f"bracketlapse-batch-{sequence}",
            self.runtime.bracket_command + [str(batch_dir), "--merge-subdirs"],
            cwd=batch_dir,
            extra_env=env,
            on_line=handle,
        )
        while child.poll() is None:
            if self.runtime.hard_stop.is_set():
                child.terminate()
                return False
            time.sleep(self.runtime.poll_interval)
        code = child.wait()
        if code != 0:
            self.runtime.log(f"永续批次 {sequence} 处理失败，退出码={code}")
            return False
        return True

    def _finish_score(self, sequence: int, batch_dir: Path, label: str, session):
        try:
            return (
                session.finish()
                if session is not None
                else self.runtime.sunset_score.process(batch_dir, label)
            )
        except TaskError as exc:
            self.runtime.log(f"永续批次 {sequence} 晚霞评分失败: {exc}")
            return False

    def _cleanup(self, sequence: int, batch_dir: Path, score_decision) -> bool:
        cleanup = self.task["cleanup"]
        if not cleanup.get("enabled"):
            return True
        try:
            keep_directories = list(cleanup["keep_directories"])
            if (
                score_decision not in (None, False)
                and score_decision.retained_hdr
                and "hdr_enfuse" not in keep_directories
            ):
                keep_directories.append("hdr_enfuse")
            cleanup_work_directory(
                batch_dir,
                keep_directories,
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
        return True

    def _check_disk(self, batch_dir: Path) -> None:
        threshold = float(self.runtime.project["disk_space_warning_threshold_gb"])
        remaining = check_disk_space(batch_dir, threshold, self.runtime.log)
        if threshold > 0 and remaining < threshold:
            self.runtime.notify_async(
                "disk_space_warning",
                f"磁盘剩余 {remaining:.2f}GB，低于阈值 {threshold:g}GB",
            )

    @staticmethod
    def _environment(data: dict[str, Any]) -> dict[str, str]:
        return {
            "BRACKLAPSE_RUN_DATE": str(data["work_date"]),
            "BRACKLAPSE_RUN_START_AT": str(data["start_at"]),
            "BRACKLAPSE_RUN_END_AT": str(data["end_at"]),
        }
