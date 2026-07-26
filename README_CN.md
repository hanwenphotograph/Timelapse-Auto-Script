# Timelapse Manager

[English](README.md) | [简体中文](README_CN.md)

Timelapse Manager 是一个跨平台 Python 延时摄影任务管理器。无界面核心负责拍摄、后期处理、持久化状态和进程控制，CLI 与 GUI 共用同一套管理服务。

关闭 GUI 后任务仍会继续运行。可以重新打开 GUI，或在另一个终端使用 CLI 查看和控制 Windows、macOS 与 Linux 上的任务。

## 功能

- 持久化任务定义、状态、阶段、进程 PID、启动时间和日志。
- 监控 worker、`camera-timelapse` 和 Bracketlapse 子进程。
- 支持手动、单次定时、永久定时和持续归档预设。
- 支持立即收尾、本轮后收尾、强制停止、重启和删除。
- 提供经过校验的任务级 YAML，以及 GUI 等宽字体编辑器。
- 支持浅色、深色和跟随系统外观。
- 支持 webhook 文本与图片通知、磁盘空间告警和异常状态恢复。
- 为当前平台生成 Debug 和 Release portable 归档。

## 内置预设

| 预设 | 行为 |
| --- | --- |
| `scheduled_once` | 把下一个清晨或黄昏时段展开为一条完整的 Manual 任务。 |
| `scheduled_loop` | 展开一条完整的 Manual 任务，并在每轮结束后创建新的 Manual 后继。 |
| `eternal` | 持续拍摄，按完整曝光组分批归档并串行处理。 |
| `manual` | 由用户填写日期、时间、工作目录和可选拍摄间隔。 |

定时预设只是配置生成器，不是运行模式。任务创建时会写入实际目录、日期、起止时间、拍摄间隔、清理策略和重试延迟。定时任务随后统一从有限 Manual 工作流运行，生成的 YAML 不含 `null`，也不包含无用的 `eternal` 配置。

`scheduled_loop` 由多条有限任务组成。每轮拥有独立 ID、YAML、状态和日志。成功轮立即启动后继；失败轮等待配置的重试延迟后创建并启动后继。任何停止或收尾操作都会禁止继续接力。同一任务链只允许一条活动任务，已有后继的历史节点不能再次启动。

系统只自动清理永久链中已成功完成的历史，默认保留 30 天。失败和停止任务会一直保留，直到用户手动删除。保留策略只删除任务元数据和日志，绝不删除照片或视频。

## 环境要求

- Python 3.10 或更高版本。
- `camera-timelapse` 可从 `PATH` 调用，或配置为绝对路径。
- 开启后期处理时需要 `brackerlapse` 或 `bracketlapse`。
- GUI 需要当前 Python 安装提供 Tk。

Debian 或 Ubuntu 可以安装 `python3-tk`。macOS 的 Homebrew Python 需要对应版本的公式，例如 Python 3.10 使用 `brew install python-tk@3.10`。

安装依赖：

```bash
python -m pip install -r requirements.txt
```

以 editable 方式安装并获得 `timelapse-manager` 命令：

```bash
python -m pip install -e .
```

## 快速开始

初始化配置和运行目录：

```bash
python timelapse.py init
```

生成的 `config/auto_timelapse.yaml` 和 `config/webhook.yaml` 默认被 Git 忽略。配置时间窗口和外部命令后验证安装：

```bash
python timelapse.py config validate
python timelapse.py self-test
```

启动 GUI：

```bash
python timelapse.py gui
```

在 GUI 中创建定时或 eternal 预设后，任务会立即在后台启动。Manual 任务的必填拍摄字段尚不完整，因此仍会先打开 YAML 编辑器。

Windows 可以打开 `start_gui.bat`，macOS 可以打开 `start_gui.command`。源码启动器依次选择当前虚拟环境、`.venv` 和 `venv`，必要时自动创建 `.venv`。debug 包会直接启动捆绑的可执行文件。

Release 包使用无控制台的 PyInstaller GUI 入口。Windows 和 Linux 直接打开捆绑的 `TimelapseManager` 可执行文件，macOS 直接打开 `TimelapseManager.app`，都不会显示控制台窗口。macOS 请保持解压后的 `.app` 与同级 `config` 目录在一起，以保留便携配置。

## CLI

列出预设与任务：

```bash
python timelapse.py preset list
python timelapse.py task list
python timelapse.py task list --json
```

创建并启动单次定时任务：

```bash
python timelapse.py task create --name "今日自动拍摄" --preset scheduled_once
python timelapse.py task start <task-id>
```

创建后立即启动永久任务链：

```bash
python timelapse.py run --name "日常延时摄影" --preset scheduled_loop
```

创建完整 Manual 任务：

```bash
python timelapse.py task create \
  --name "手动测试" \
  --preset manual \
  --work-dir ./output/manual \
  --start-date 2026-07-22 \
  --start-at 03:00 \
  --end-date 2026-07-22 \
  --end-at 09:00 \
  --interval 6
```

查看任务、日志和受控进程：

```bash
python timelapse.py task show <task-id>
python timelapse.py task logs <task-id> --follow
python timelapse.py process list
```

控制任务：

```bash
python timelapse.py task finish <task-id>
python timelapse.py task finish-after-current <task-id>
python timelapse.py task stop <task-id>
python timelapse.py task restart <task-id>
```

`finish` 会结束当前拍摄并处理可用素材。`finish-after-current` 会等待当前有限任务或 eternal 批次结束。`stop` 会终止 worker 和全部受控子进程。这三种操作都会终止永久链接力。

在当前终端运行选定任务：

```bash
python timelapse.py task start <task-id> --foreground
```

永久链只有选定轮次在前台运行，后继任务会作为普通后台任务启动。

## 配置

完整项目配置见 `config/auto_timelapse.example.yaml`。常用字段包括：

- `auto_root`
- `capture_interval_seconds`
- `morning.start_at` / `morning.end_at`
- `dusk.start_at` / `dusk.end_at`
- `commands.camera` / `commands.bracketlapse`
- `runtime.retry_delay_seconds`
- `runtime.task_history_retention_days`

可以从 CLI 设置任意点分隔字段：

```bash
python timelapse.py config set morning.start_at "'04:00'"
python timelapse.py config set runtime.task_history_retention_days 30
```

展开后的永久任务包含不可变链身份和可编辑的接力开关：

```yaml
schema_version: 2
preset: manual
capture:
  work_dir: /absolute/path/2026-07-22/0300-0900
  start_date: '2026-07-22'
  start_at: '03:00'
  end_date: '2026-07-22'
  end_at: '09:00'
  interval_seconds: 6
continuation:
  enabled: true
  chain_id: scheduled-loop-...
  chain_name: 日常延时摄影
  sequence: 1
  source_preset: scheduled_loop
```

在空闲链叶子启动前把 `continuation.enabled` 改为 `false`，可以只运行当前轮。链身份、序号和前驱字段不可编辑。运行中的任务 YAML 也不能修改。

旧 `scheduled_once` 和 `scheduled_loop` 任务会在空闲状态下首次加载时完成一次性迁移。活动中的旧任务保持不变，直到进入终态后再迁移。

## 运行数据

任务状态默认位于 `.timelapse/tasks/<task-id>/`，其中包含 `state.json`、`task.log` 和控制队列。写入过程使用临时文件、原子替换和进程感知锁。

Eternal 任务把暂存数据和跨平台 YAML 队列放在 `<auto_root>/.eternal/`。处理失败的清单会保留到下次运行重试。

## 打包

PyInstaller 不支持交叉编译，因此需要在每个目标系统上分别构建：

```bash
python -m pip install -r requirements-dev.txt
python scripts/build_debug.py
```

Debug 归档输出到：

```text
bin/Debug-Archives/TimelapseManager-<win|mac|linux>-debug-portable-<yymmdd-hhmmss>.zip
```

构建不显示控制台窗口的 Release GUI 包：

```bash
python scripts/build_release.py
```

Release 归档输出到：

```text
bin/Release-Archives/TimelapseManager-<win|mac|linux>-release-portable-<yymmdd-hhmmss>.zip
```

## 开发与测试

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python timelapse.py self-test
```

集成测试使用模拟相机和 Bracketlapse，并实际启动后台 worker，覆盖成功与失败接力、优雅控制、清理和 eternal 分批处理。
