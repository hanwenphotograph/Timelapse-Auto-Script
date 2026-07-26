"""Command-line interface for all Timelapse Manager operations."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from timelapse_manager import __version__
from timelapse_manager.diagnostics import run_self_test
from timelapse_manager.errors import ConfigError, TimelapseError
from timelapse_manager.io_utils import load_yaml, now_iso, save_yaml, yaml_text
from timelapse_manager.presets import PRESET_DESCRIPTIONS
from timelapse_manager.service import ManagerService
from timelapse_manager.worker import run_worker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="timelapse-manager",
        description="跨平台延时摄影任务、进程和配置管理器",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("--root", type=Path, help="项目根目录，默认自动检测")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="创建默认 YAML 和运行目录")
    commands.add_parser("gui", help="启动图形界面")

    preset = commands.add_parser("preset", help="查看内置任务预设")
    preset_sub = preset.add_subparsers(dest="preset_command", required=True)
    preset_sub.add_parser("list", help="列出预设")

    config = commands.add_parser("config", help="管理项目级 YAML")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    for name, help_text in (
        ("show", "显示配置"),
        ("path", "显示配置路径"),
        ("validate", "校验配置"),
    ):
        item = config_sub.add_parser(name, help=help_text)
        item.add_argument("--kind", choices=("project", "webhook"), default="project")
    config_set = config_sub.add_parser("set", help="设置点分隔路径的 YAML 值")
    config_set.add_argument("key", help="例如 morning.start_at")
    config_set.add_argument("value", help="YAML 标量或结构，例如 04:00、true、[a,b]")
    config_set.add_argument("--kind", choices=("project", "webhook"), default="project")

    task = commands.add_parser("task", help="创建、启动和控制任务")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    create = task_sub.add_parser("create", help="按预设创建任务 YAML，任务不会自动启动")
    create.add_argument("--name", required=True)
    create.add_argument("--preset", choices=tuple(PRESET_DESCRIPTIONS), required=True)
    create.add_argument("--id")
    create.add_argument("--work-dir")
    create.add_argument("--start-date")
    create.add_argument("--start-at")
    create.add_argument("--end-date")
    create.add_argument("--end-at")
    create.add_argument("--interval", type=float)

    list_parser = task_sub.add_parser("list", help="列出任务及状态")
    list_parser.add_argument("--json", action="store_true")
    show = task_sub.add_parser("show", help="显示任务定义、状态和路径")
    show.add_argument("task_id")
    show.add_argument("--json", action="store_true")
    task_set = task_sub.add_parser("set", help="修改任务 YAML 中的点分隔字段")
    task_set.add_argument("task_id")
    task_set.add_argument("key")
    task_set.add_argument("value")
    start = task_sub.add_parser("start", help="手动启动任务")
    start.add_argument("task_id")
    start.add_argument("--foreground", action="store_true", help="在当前终端前台运行")
    for name, help_text in (
        ("stop", "强制停止任务并终止全部子进程"),
        ("finish", "立即停止拍摄，完成后期处理后结束"),
        ("finish-after-current", "当前时段或永续整批完成后结束"),
        ("restart", "停止后重新启动任务"),
    ):
        item = task_sub.add_parser(name, help=help_text)
        item.add_argument("task_id")
    delete = task_sub.add_parser("delete", help="删除已停止任务的定义")
    delete.add_argument("task_id")
    delete.add_argument(
        "--purge-runtime", action="store_true", help="同时删除该任务日志和状态"
    )
    logs = task_sub.add_parser("logs", help="显示任务日志")
    logs.add_argument("task_id")
    logs.add_argument("--lines", type=int, default=100)
    logs.add_argument("--follow", "-f", action="store_true")

    run = commands.add_parser("run", help="创建任务并手动启动")
    run.add_argument("--name", default="命令行任务")
    run.add_argument("--preset", choices=tuple(PRESET_DESCRIPTIONS), required=True)
    run.add_argument("--foreground", action="store_true")

    process = commands.add_parser("process", help="查看和管理受控进程")
    process_sub = process.add_subparsers(dest="process_command", required=True)
    process_list = process_sub.add_parser(
        "list", help="以列表形式显示工作进程和外部子进程"
    )
    process_list.add_argument("--json", action="store_true")
    process_stop = process_sub.add_parser("stop", help="停止列表中的指定 PID")
    process_stop.add_argument("pid", type=int)

    self_test = commands.add_parser("self-test", help="运行无需相机的命令行自测")
    self_test.add_argument("--full", action="store_true", help="外部命令缺失也视为失败")

    worker = commands.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--task", required=True)
    worker.add_argument("--console", action="store_true")
    return parser


def _parse_value(value: str) -> Any:
    try:
        return yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise ConfigError(f"值不是合法 YAML: {exc}") from exc


def _set_nested(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    keys = [part for part in dotted_key.split(".") if part]
    if not keys:
        raise ConfigError("配置键不能为空")
    current = data
    for key in keys[:-1]:
        child = current.get(key)
        if child is None:
            child = {}
            current[key] = child
        if not isinstance(child, dict):
            raise ConfigError(f"{key} 已存在且不是映射，无法继续设置")
        current = child
    current[keys[-1]] = value


def _print_table(headers: list[str], rows: list[list[Any]]) -> None:
    if not rows:
        print("（无记录）")
        return
    values = [["" if value is None else str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        for index, value in enumerate(row):
            widths[index] = min(max(widths[index], len(value)), 60)
    print(
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    )
    print("  ".join("-" * width for width in widths))
    for row in values:
        print(
            "  ".join(
                value[: widths[index]].ljust(widths[index])
                for index, value in enumerate(row)
            )
        )


def _foreground_start(service: ManagerService, task_id: str) -> int:
    service.prepare_foreground_task(task_id)
    code = run_worker(task_id, service.paths.root, console=True)
    state = service.store.read_state(task_id, reconcile=True)
    if state["status"] == "starting" and state.get("runner_pid") is None:
        state.update(
            {
                "status": "failed",
                "phase": "工作进程初始化失败",
                "message": "前台工作进程未能初始化",
                "ended_at": now_iso(),
                "exit_code": code,
            }
        )
        service.store.write_state(task_id, state)
    return code


def _tail(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return "".join(handle.readlines()[-max(lines, 1) :])


def _handle_config(service: ManagerService, args: argparse.Namespace) -> int:
    manager = service.config_manager
    if args.config_command == "show":
        print(manager.normalized_text(args.kind), end="")
    elif args.config_command == "path":
        print(
            manager.paths.config_file
            if args.kind == "project"
            else manager.paths.webhook_file
        )
    elif args.config_command == "validate":
        manager.load()
        print(f"{args.kind} 配置校验通过")
    elif args.config_command == "set":
        path = (
            manager.paths.config_file
            if args.kind == "project"
            else manager.paths.webhook_file
        )
        data = load_yaml(path)
        _set_nested(data, args.key, _parse_value(args.value))
        text = yaml_text(data)
        manager.validate_text(args.kind, text)
        save_yaml(path, data)
        service.reload()
        print(f"已更新 {args.kind} 配置: {args.key}")
    return 0


def _handle_task(service: ManagerService, args: argparse.Namespace) -> int:
    command = args.task_command
    if command == "create":
        task = service.create_task(args.name, args.preset, args.id)
        capture_values = {
            "work_dir": args.work_dir,
            "start_date": args.start_date,
            "start_at": args.start_at,
            "end_date": args.end_date,
            "end_at": args.end_at,
            "interval_seconds": args.interval,
        }
        if any(value is not None for value in capture_values.values()):
            task["capture"].update(
                {
                    key: value
                    for key, value in capture_values.items()
                    if value is not None
                }
            )
            service.store.save_text(task["id"], yaml_text(task))
        print(task["id"])
        print(service.store.definition_path(task["id"]))
    elif command == "list":
        items = service.list_tasks()
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            _print_table(
                ["ID", "名称", "预设", "状态", "阶段", "PID"],
                [
                    [
                        item["task"]["id"],
                        item["task"]["name"],
                        item["task"]["preset"],
                        item["state"]["status"],
                        item["state"]["phase"],
                        item["state"].get("runner_pid"),
                    ]
                    for item in items
                ],
            )
    elif command == "show":
        detail = service.task_details(args.task_id)
        if args.json:
            print(json.dumps(detail, ensure_ascii=False, indent=2))
        else:
            print(yaml_text(detail["task"]), end="")
            print("运行状态:")
            print(json.dumps(detail["state"], ensure_ascii=False, indent=2))
            print(f"任务文件: {detail['definition_path']}")
            print(f"日志文件: {detail['log_path']}")
    elif command == "set":
        task = service.store.load(args.task_id)
        _set_nested(task, args.key, _parse_value(args.value))
        service.store.save_text(args.task_id, yaml_text(task))
        print(f"已更新任务 {args.task_id}: {args.key}")
    elif command == "start":
        if args.foreground:
            return _foreground_start(service, args.task_id)
        state = service.start_task(args.task_id)
        print(f"任务已启动: {args.task_id}, PID={state.get('runner_pid')}")
    elif command == "stop":
        service.request(args.task_id, "stop")
        print("已发送强制停止请求")
    elif command == "finish":
        service.request(args.task_id, "finish_now")
        print("已发送立即结束拍摄并完成处理请求")
    elif command == "finish-after-current":
        service.request(args.task_id, "finish_after_current")
        print("已发送当前任务或批次完成后停止请求")
    elif command == "restart":
        state = service.restart_task(args.task_id)
        print(f"任务已重新启动，PID={state.get('runner_pid')}")
    elif command == "delete":
        service.delete_task(args.task_id, purge_runtime=args.purge_runtime)
        print(f"已删除任务: {args.task_id}")
    elif command == "logs":
        path = service.store.log_path(args.task_id)
        print(_tail(path, args.lines), end="")
        if args.follow:
            try:
                previous = path.stat().st_size if path.exists() else 0
                while True:
                    time.sleep(0.5)
                    if not path.exists():
                        continue
                    size = path.stat().st_size
                    if size < previous:
                        previous = 0
                    if size > previous:
                        with path.open(
                            "r", encoding="utf-8", errors="replace"
                        ) as handle:
                            handle.seek(previous)
                            print(handle.read(), end="", flush=True)
                        previous = size
            except KeyboardInterrupt:
                return 0
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "_worker":
        return run_worker(args.task, args.root, console=args.console)
    try:
        service = ManagerService(args.root)
        if args.command == "init":
            print(json.dumps(service.initialize(), ensure_ascii=False, indent=2))
        elif args.command == "gui":
            from timelapse_manager.gui import launch_gui

            launch_gui(service.paths.root)
        elif args.command == "preset":
            _print_table(
                ["预设", "说明"],
                [
                    [name, description]
                    for name, description in PRESET_DESCRIPTIONS.items()
                ],
            )
        elif args.command == "config":
            return _handle_config(service, args)
        elif args.command == "task":
            return _handle_task(service, args)
        elif args.command == "run":
            task = service.create_task(args.name, args.preset)
            if args.foreground:
                return _foreground_start(service, task["id"])
            state = service.start_task(task["id"])
            print(f"任务 {task['id']} 已启动，PID={state.get('runner_pid')}")
        elif args.command == "process":
            if args.process_command == "list":
                processes = service.list_processes()
                if args.json:
                    print(json.dumps(processes, ensure_ascii=False, indent=2))
                else:
                    _print_table(
                        ["任务", "角色", "PID", "状态", "启动时间", "命令"],
                        [
                            [
                                process["task_id"],
                                process["role"],
                                process["pid"],
                                process["status"],
                                process.get("started_at"),
                                process.get("command"),
                            ]
                            for process in processes
                        ],
                    )
            else:
                service.stop_process(args.pid)
                print(f"已请求停止 PID {args.pid}")
        elif args.command == "self-test":
            results = run_self_test(service, full=args.full)
            _print_table(
                ["结果", "检查项", "详情"],
                [[item.level, item.name, item.detail] for item in results],
            )
            return 1 if any(item.level == "FAIL" for item in results) else 0
        return 0
    except (TimelapseError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
