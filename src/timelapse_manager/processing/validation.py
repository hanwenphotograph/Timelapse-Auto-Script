"""Validation of persisted processing-only jobs."""

from datetime import datetime

from timelapse_manager.errors import ConfigError


def validate_processing_task(task):
    data = task.get("deferred_processing")
    if not isinstance(data, dict) or not isinstance(data.get("spec"), dict):
        raise ConfigError("集中处理任务缺少素材信息")
    for key in ("source_task_id", "ready_at"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ConfigError(f"deferred_processing.{key} 不能为空")
    try:
        datetime.fromisoformat(data["ready_at"])
    except ValueError as exc:
        raise ConfigError("集中处理排队时间无效") from exc
    for key in ("work_dir", "label", "start_date", "start_at", "end_date", "end_at"):
        if not isinstance(data["spec"].get(key), str) or not data["spec"][key]:
            raise ConfigError(f"集中处理素材缺少 {key}")
    if type(data.get("rounds")) is not int or data["rounds"] < 0:
        raise ConfigError("集中处理照片组数无效")
    if not isinstance(data.get("capture_started"), bool):
        raise ConfigError("集中处理拍摄状态无效")
    names = data.get("preserve_names")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ConfigError("集中处理保留文件列表无效")
    if task.get("continuation") or not task["processing"]["enabled"]:
        raise ConfigError("集中处理任务必须启用处理且不能接力拍摄")
