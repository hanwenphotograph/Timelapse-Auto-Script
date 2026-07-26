# Timelapse Manager

[English](README.md) | [简体中文](README_CN.md)

Timelapse Manager is a cross-platform Python application for creating, running, and monitoring timelapse capture tasks. Its headless core owns capture, post-processing, persistent state, and process control; the CLI and GUI use the same management service.

Tasks continue running after the GUI closes. Reopen the GUI or use the CLI from another terminal to inspect and control them on Windows, macOS, or Linux.

## Features

- Persistent task definitions, statuses, phases, process IDs, start times, and logs.
- Process monitoring for workers, `camera-timelapse`, and Bracketlapse children.
- Manual, one-shot scheduled, recurring scheduled, and continuous archive presets.
- Graceful finish, finish-after-current, forced stop, restart, and deletion controls.
- Per-task YAML with validation and a monospace editor in the GUI.
- Light, dark, and system appearance modes.
- Webhook notifications, image notifications, disk-space warnings, and stale-process reconciliation.
- Debug and Release portable archives for the current platform.

## Presets

| Preset | Behavior |
| --- | --- |
| `scheduled_once` | Materializes the next morning or dusk slot as one complete Manual task. |
| `scheduled_loop` | Materializes one complete Manual task and creates a new Manual successor after every round. |
| `eternal` | Captures continuously, archives complete exposure groups in batches, and processes batches serially. |
| `manual` | Leaves the date, time, working directory, and optional interval for the user to configure. |

Scheduled presets are configuration generators, not runtime modes. Their task YAML is written at creation time with an actual directory, dates, times, interval, cleanup behavior, and retry delay. Scheduled task files therefore run through the same finite Manual workflow and contain no `null` values or unused `eternal` settings.

A `scheduled_loop` is a chain of finite tasks. Each round has its own ID, YAML, state, and log. A successful round starts its successor immediately; a failed round waits for its configured retry delay before creating and starting a successor. Any stop or finish action prevents further handoff. A chain permits only one active task and completed historical nodes cannot be restarted after they have a successor.

Only completed recurring-chain history is removed automatically. The default retention is 30 days; failed and stopped tasks remain until manually deleted. Retention removes task metadata and logs, never captured photos or videos.

## Requirements

- Python 3.10 or newer.
- `camera-timelapse` available on `PATH` or configured with an absolute path.
- `brackerlapse` or `bracketlapse` available when post-processing is enabled.
- Tk supplied by the Python installation for the GUI.

On Debian or Ubuntu, install `python3-tk`. Homebrew Python users on macOS need the matching formula, such as `brew install python-tk@3.10` for Python 3.10.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

For an editable installation and the `timelapse-manager` command:

```bash
python -m pip install -e .
```

## Quick Start

Initialize configuration and runtime directories:

```bash
python timelapse.py init
```

The generated `config/auto_timelapse.yaml` and `config/webhook.yaml` files are ignored by Git. Configure schedule windows and external commands, then validate the installation:

```bash
python timelapse.py config validate
python timelapse.py self-test
```

Start the GUI:

```bash
python timelapse.py gui
```

Scheduled and eternal presets created in the GUI start immediately in the background. Manual tasks open the YAML editor first because their required capture fields are not complete yet.

Windows users can open `start_gui.bat`; macOS users can open `start_gui.command`. Source launchers prefer an active virtual environment, then `.venv`, then `venv`, and create `.venv` when necessary. Debug packages launch the bundled executable directly.

Release packages are built with a windowed PyInstaller entry point. On Windows and Linux, launch the bundled `TimelapseManager` executable directly; on macOS, open `TimelapseManager.app`. Neither Release entry point opens a console window. Keep the extracted macOS `.app` beside its bundled `config` directory so portable configuration remains available.

## CLI

List presets and tasks:

```bash
python timelapse.py preset list
python timelapse.py task list
python timelapse.py task list --json
```

Create and start a one-shot scheduled task:

```bash
python timelapse.py task create --name "Today's capture" --preset scheduled_once
python timelapse.py task start <task-id>
```

Create and immediately start a recurring chain:

```bash
python timelapse.py run --name "Daily timelapse" --preset scheduled_loop
```

Create a fully specified Manual task:

```bash
python timelapse.py task create \
  --name "Manual test" \
  --preset manual \
  --work-dir ./output/manual \
  --start-date 2026-07-22 \
  --start-at 03:00 \
  --end-date 2026-07-22 \
  --end-at 09:00 \
  --interval 6
```

Inspect tasks, logs, and managed processes:

```bash
python timelapse.py task show <task-id>
python timelapse.py task logs <task-id> --follow
python timelapse.py process list
```

Control a task:

```bash
python timelapse.py task finish <task-id>
python timelapse.py task finish-after-current <task-id>
python timelapse.py task stop <task-id>
python timelapse.py task restart <task-id>
```

`finish` ends the current capture and processes usable material. `finish-after-current` waits for the current finite task or eternal batch. `stop` terminates the worker and all managed children. All three actions also end recurring-chain handoff.

Run the selected task in the current terminal:

```bash
python timelapse.py task start <task-id> --foreground
```

For recurring chains, only the selected round stays in the foreground. Its successor starts as a normal background task.

## Configuration

See `config/auto_timelapse.example.yaml` for all project settings. Common fields include:

- `auto_root`
- `capture_interval_seconds`
- `morning.start_at` / `morning.end_at`
- `dusk.start_at` / `dusk.end_at`
- `commands.camera` / `commands.bracketlapse`
- `runtime.retry_delay_seconds`
- `runtime.task_history_retention_days`

Set any dotted field from the CLI:

```bash
python timelapse.py config set morning.start_at "'04:00'"
python timelapse.py config set runtime.task_history_retention_days 30
```

A materialized recurring task includes immutable chain identity and an editable handoff switch:

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
  chain_name: Daily timelapse
  sequence: 1
  source_preset: scheduled_loop
```

Set `continuation.enabled` to `false` before starting an idle chain leaf to run it only once. Chain identity, sequence, and predecessor fields cannot be edited. Running task YAML is locked against changes.

Legacy `scheduled_once` and `scheduled_loop` task files are migrated once when loaded while inactive. Active legacy tasks are left untouched until they reach a terminal state.

## Runtime Data

Task state defaults to `.timelapse/tasks/<task-id>/`, containing `state.json`, `task.log`, and queued controls. Writes use temporary files, atomic replacement, and process-aware locks.

Eternal tasks store staging data and portable YAML queues under `<auto_root>/.eternal/`. Failed processing manifests remain available for retry on the next run.

## Packaging

Build on each target operating system because PyInstaller does not cross-compile:

```bash
python -m pip install -r requirements-dev.txt
python scripts/build_debug.py
```

Debug archives are written to:

```text
bin/Debug-Archives/TimelapseManager-<win|mac|linux>-debug-portable-<yymmdd-hhmmss>.zip
```

Build a Release GUI package without a console window:

```bash
python scripts/build_release.py
```

Release archives are written to:

```text
bin/Release-Archives/TimelapseManager-<win|mac|linux>-release-portable-<yymmdd-hhmmss>.zip
```

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python timelapse.py self-test
```

The integration suite uses fake camera and Bracketlapse commands, including real detached workers, successful and failed recurring handoffs, graceful controls, cleanup, and eternal batch processing.
