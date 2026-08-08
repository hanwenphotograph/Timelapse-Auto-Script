"""Post-process one archived eternal-capture batch."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from timelapse_manager.bracketlapse import parse_hdr_ready, parse_video_progress
from timelapse_manager.errors import TaskError
from timelapse_manager.runtime import TaskRuntime
from timelapse_manager.workflows.eternal_finish import EternalBatchFinisher


class EternalBatchProcessor:
    def __init__(
        self,
        runtime: TaskRuntime,
        state_dir: Path,
        capture_dir: Path,
        album_lock: Any,
    ):
        self.runtime = runtime
        self.task = runtime.task
        self.finisher = EternalBatchFinisher(
            runtime,
            state_dir,
            capture_dir,
            album_lock,
        )

    def process(self, data: dict[str, Any]) -> bool:
        sequence = int(data["sequence"])
        batch_dir = Path(str(data["batch_dir"]))
        self.runtime.set_phase(
            "永续批次 HDR 处理", f"批次 {sequence}，目录 {batch_dir}"
        )
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
        if not self._run_bracket(
            sequence,
            batch_dir,
            env,
            score_session,
            len(data.get("groups", [])),
        ):
            return False
        score_decision = self._finish_score(sequence, batch_dir, label, score_session)
        if score_decision is False:
            return False
        if score_decision is None and not self.runtime.sunset_score.enabled:
            self.runtime.webhook.notify_image(
                "webhook-image", f"图片推送：{label}", batch_dir
            )
        try:
            final_dir = self.finisher.finish(sequence, batch_dir, score_decision)
        except TaskError:
            return False
        if final_dir is None:
            return False
        self.runtime.notify_async(
            "ended", f"永续批次 {sequence} 已完成处理、导出和清理，目录 {final_dir}"
        )
        return True

    def _run_bracket(
        self,
        sequence: int,
        batch_dir: Path,
        env: dict[str, str],
        score_session,
        total: int,
    ) -> bool:
        role = f"bracketlapse-batch-{sequence}"
        video_started = False

        def handle(line: str) -> None:
            nonlocal video_started
            event = parse_hdr_ready(line, batch_dir)
            if event is not None:
                self.runtime.set_child_progress(
                    role,
                    completed=event.frame_number,
                    stage="hdr",
                    phase="HDR处理",
                )
                if score_session is not None:
                    score_session.scan()
            if "Fusing " in line:
                self.runtime.set_phase("永续批次 HDR 融合", str(batch_dir))
            elif "Deflickering fused frames." in line:
                self.runtime.set_phase("永续批次去闪", str(batch_dir))
            video_event = parse_video_progress(line, batch_dir)
            if video_event is not None:
                self.runtime.set_child_progress(
                    role,
                    completed=video_event.completed,
                    total=video_event.total,
                    stage="video",
                    phase="视频处理",
                )
                if not video_started:
                    video_started = True
                    self.runtime.set_phase("永续批次视频导出", str(batch_dir))
            elif "Creating video from " in line:
                video_started = True
                self.runtime.set_child_progress(
                    role,
                    completed=0,
                    total=0,
                    stage="video",
                    phase="视频处理",
                )
                self.runtime.set_phase("永续批次视频导出", str(batch_dir))

        child = self.runtime.spawn(
            role,
            self.runtime.bracket_command + [str(batch_dir), "--merge-subdirs"],
            cwd=batch_dir,
            extra_env=env,
            on_line=handle,
        )
        self.runtime.set_child_progress(
            role,
            completed=0,
            total=total,
            stage="hdr",
            phase="HDR处理",
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

    @staticmethod
    def _environment(data: dict[str, Any]) -> dict[str, str]:
        return {
            "BRACKLAPSE_RUN_DATE": str(data["work_date"]),
            "BRACKLAPSE_RUN_START_AT": str(data["start_at"]),
            "BRACKLAPSE_RUN_END_AT": str(data["end_at"]),
        }
