"""Declarative, typed fields for the configuration forms."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    path: str
    label: str
    kind: str = "text"


PROJECT_GROUPS = (
    (
        "照片与后期处理",
        (
            Field("auto_root", "照片输出目录", "directory"),
            Field("photo_processing.mode", "照片处理时间", "mode"),
            Field("photo_processing.start_at", "每天开始处理时间（HH:MM）"),
            Field("capture_interval_seconds", "拍摄间隔（秒）", "float"),
            Field("watch_quiet_seconds", "导出前静默间隔（秒）", "float"),
            Field(
                "disk_space_warning_threshold_gb", "磁盘告警阈值（GB，0 关闭）", "float"
            ),
            Field("sunset_score.interval", "晚霞评分采样间隔（张）", "int"),
        ),
    ),
    (
        "清晨与黄昏拍摄时段",
        (
            Field("morning.start_at", "清晨开始时间（HH:MM）"),
            Field("morning.end_at", "清晨结束时间（HH:MM）"),
            Field("dusk.start_at", "黄昏开始时间（HH:MM）"),
            Field("dusk.end_at", "黄昏结束时间（HH:MM）"),
        ),
    ),
    (
        "外部命令",
        (
            Field("commands.camera", "相机命令"),
            Field("commands.bracketlapse", "Bracketlapse 命令"),
            Field("commands.bracketlapse_fallback", "Bracketlapse 备用命令"),
            Field("commands.sunsetscore", "SunsetScore 命令"),
        ),
    ),
    (
        "运行与重试",
        (
            Field("runtime.state_dir", "运行状态目录", "directory"),
            Field("runtime.tasks_dir", "任务配置目录", "directory"),
            Field("runtime.poll_interval_seconds", "控制轮询间隔（秒）", "float"),
            Field("runtime.startup_probe_seconds", "启动检测时间（秒）", "float"),
            Field("runtime.stop_timeout_seconds", "停止超时（秒）", "float"),
            Field("runtime.retry_delay_seconds", "失败重试间隔（秒）", "float"),
            Field("runtime.max_retry_attempts", "连续重试上限", "int"),
            Field("runtime.task_history_retention_days", "成功任务保留天数", "int"),
        ),
    ),
    (
        "永续拍摄",
        (
            Field("eternal.batch_groups", "每批曝光组数", "int"),
            Field("eternal.images_per_group", "每组照片数量", "int"),
            Field("eternal.queue_poll_seconds", "处理队列轮询间隔（秒）", "float"),
            Field("eternal.archive_retry_seconds", "归档重试间隔（秒）", "float"),
        ),
    ),
)

WEBHOOK_GROUPS = (
    (
        "Webhook 通知",
        (
            Field("enabled", "启用任务通知", "bool"),
            Field("url", "机器人 Webhook 地址"),
            Field("body", "文本消息模板", "multiline"),
            Field("push_image", "推送图片", "bool"),
            Field("image_body", "图片消息模板", "multiline"),
        ),
    ),
)

MODE_LABELS = {"即时": "immediate", "自定义时间": "scheduled"}
