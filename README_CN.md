# Timelapse Manager

[English](README.md) | [简体中文](README_CN.md)

![Timelapse Manager 运行总览](docs/images/timelapse-manager-overview.png)

Timelapse Manager 是一个跨平台的延时摄影任务管理器，同时提供 GUI 与 CLI。它把 Camera Timelapse Controller、Bracketlapse、可选的 SunsetScore 分析和消息通知连接成可持久运行的任务流程。

关闭 GUI 不会停止后台任务。重新打开程序即可继续查看进度、日志和受控进程。

## 主要功能

- 创建手动、单次定时、循环定时或持续拍摄任务。
- 查看任务状态、进度、日志、工作进程和外部子程序。
- 在后台执行可恢复的拍摄与后期处理流程。
- 在 GUI 中编辑并校验 YAML 配置。
- 检查并安装受支持的工作流依赖。
- 可选发送企业微信文本与图片通知。

## 运行项目

### 环境要求

- Python 3.10 或更高版本。
- 当前 Python 安装包含 Tk。
- 实际拍摄需要 Camera Timelapse Controller。
- 开启后期处理时需要 Bracketlapse 0.2.0 或更高版本。

即使尚未安装外部工作流工具，GUI 也可以正常启动。启动后可通过“包管理”检查或安装受支持的依赖。

### 下载

```bash
git clone https://github.com/hanwenphotograph/Timelapse-Auto-Script.git
cd Timelapse-Auto-Script
```

也可以下载仓库 ZIP 并解压。

### macOS

双击 `start_gui.command`。启动器会选择或创建虚拟环境、安装缺少的 Python 包、检查 Tk，并使用 `TL` 程序坞图标启动 GUI。

### Windows

双击 `start_gui.bat`。启动器会完成相同的环境与包检查，然后打开 GUI。

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python timelapse.py gui
```

Debian 或 Ubuntu 缺少 Tk 时先执行：

```bash
sudo apt install python3-tk
```

如果使用打包后的 Release，macOS 打开 `TimelapseManager.app`，Windows 和 Linux 直接运行 `TimelapseManager` 可执行文件。

## 第一次使用

1. 打开“包管理”，检查 Camera Timelapse Controller 与 Bracketlapse。
2. 打开“配置中心”，确认拍摄时间、输出目录和外部命令。
3. 打开“任务管理”，点击“新建任务”，输入名称并选择预设。
4. 通过“运行总览”“进程监控”和“运行日志”查看任务。
5. 使用任务操作正常收尾、本轮后收尾或立即停止。

| 预设 | 适用场景 |
| --- | --- |
| `scheduled_once` | 下一个已配置的清晨或黄昏时段。 |
| `scheduled_loop` | 每轮完成后自动创建下一条清晨或黄昏任务。 |
| `eternal` | 持续拍摄，并分批归档和处理。 |
| `manual` | 手动指定目录、日期、时段和间隔。 |

手动任务需要先在 YAML 编辑器中补全参数。定时和 eternal 任务创建后会在后台启动。

## 常用命令

```bash
python timelapse.py init          # 创建配置文件
python timelapse.py self-test     # 检查 Python 与外部工具
python timelapse.py gui           # 打开 GUI
python timelapse.py task list     # 列出任务
python timelapse.py process list  # 列出受控进程
```

运行 `python timelapse.py --help`，或在子命令后添加 `--help`，可以查看完整 CLI 帮助。

## 可选功能

### 企业微信 Webhook

打开“配置中心”并选择“Webhook”，填写机器人地址和企业微信模板：

```yaml
enabled: false
url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
body: '{"msgtype":"text","text":{"content":"__CONTENT__"}}'
push_image: true
image_body: '{"msgtype":"image","image":{"base64":"__IMGBASE64__","md5":"__IMGMD5__"}}'
```

点击“测试文本和图片”会先校验并保存编辑器内容，再依次发送两条测试消息。即使正式通知尚未启用，也可以执行测试。

![企业微信 Webhook 配置](docs/images/timelapse-manager-webhook.png)

### SunsetScore

SunsetScore 0.10.0 或更高版本可以抽样分析处理后的照片并识别晚霞。检测到晚霞时保留 `hdr_enfuse`，未检测到时删除该目录；分析失败时保留照片并让任务安全失败。可以从“包管理”安装或准备依赖，也可以单独使用 `pipx` 安装 CLI。

拍摄和后期处理采用依赖公开协议。Bracketlapse 0.2.0 或更高版本会保持一个 standby 进程，在每个完整曝光组就绪后立即融合并发出 `hdr_ready` 事件。Manager 将事件转发给 SunsetScore 0.10.0 或更高版本的 JSONL 常驻服务，由该服务负责目录扫描、采样、聚合和评分文件写入，并在同一任务的所有帧及永续批次中复用一个模型。HDR 生产完成后再收尾去闪和视频导出，评分可以并行继续。Manager 不会探测两个依赖的内部 Python 环境，也不会复制其内部实现。

### 界面外观

使用侧边栏底部的控件切换跟随系统、浅色或深色外观。

## 配置字段

GUI 会自动创建 `config/auto_timelapse.yaml` 和 `config/webhook.yaml`，同目录提供了示例文件。

| 项目配置字段 | 含义 |
| --- | --- |
| `schema_version` | 配置格式版本，通常无需修改。 |
| `auto_root` | 定时与持续任务的基础输出目录。 |
| `capture_interval_seconds` | 拍摄组之间的默认间隔。 |
| `watch_quiet_seconds` | Bracketlapse standby 在最终去闪和视频导出前使用的静默间隔。 |
| `disk_space_warning_threshold_gb` | 剩余空间告警阈值，`0` 表示关闭。 |
| `morning.start_at` / `morning.end_at` | 清晨定时时段。 |
| `dusk.start_at` / `dusk.end_at` | 黄昏定时时段。 |
| `commands.camera` | Camera Timelapse Controller 命令或绝对路径。 |
| `commands.bracketlapse` | Bracketlapse 主命令。 |
| `commands.bracketlapse_fallback` | Bracketlapse 备用名称或路径。 |
| `commands.sunsetscore` | SunsetScore 命令或绝对路径。 |
| `sunset_score.interval` | 每隔多少张处理后照片进行一次评分。 |
| `runtime.state_dir` / `runtime.tasks_dir` | 运行状态与任务定义目录。 |
| `runtime.poll_interval_seconds` | worker 检查控制指令的间隔。 |
| `runtime.startup_probe_seconds` | 新 worker 报告启动状态的等待时间。 |
| `runtime.stop_timeout_seconds` | 强制终止前等待正常停止的时间。 |
| `runtime.retry_delay_seconds` | 循环任务失败后的重试延迟。 |
| `runtime.task_history_retention_days` | 已完成循环任务历史的保留天数。 |
| `eternal.batch_groups` | 每个持续任务批次包含的完整曝光组数量。 |
| `eternal.images_per_group` | 每个曝光组预期包含的照片数量。 |
| `eternal.queue_poll_seconds` | 持续任务队列的检查间隔。 |
| `eternal.archive_retry_seconds` | 归档失败后的重试延迟。 |

| Webhook 字段 | 含义 |
| --- | --- |
| `enabled` | 启用正式任务通知。 |
| `url` | 企业微信机器人 Webhook 地址。 |
| `body` | 包含 `__CONTENT__` 的文本 JSON 模板。 |
| `push_image` | 在文本通知后继续发送任务图片。 |
| `image_body` | 包含 `__IMGBASE64__` 和 `__IMGMD5__` 的图片 JSON 模板。 |

## 数据与安全

- 任务定义保存在 `config/tasks/`。
- 运行状态和日志保存在 `.timelapse/tasks/`。
- 删除任务元数据不会删除已拍摄的照片或视频。
- 清理策略可能删除任务工作目录中未保留的内容，SunsetScore 也可能删除 `hdr_enfuse`，请先用少量样例素材验证流程。

## 开发与打包

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/build_debug.py
python scripts/build_release.py
```

## 程序图标

<p align="center">
  <img src="src/timelapse_manager/assets/timelapse-manager.png" alt="Timelapse Manager TL 应用图标" width="128" height="128">
</p>
