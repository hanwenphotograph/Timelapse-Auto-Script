"""Score suffixes for managed date and time album directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from timelapse_manager.errors import ConfigError, TaskError
from timelapse_manager.io_utils import load_yaml, save_yaml


_DATE_ALBUM = re.compile(r"^(?P<base>\d{4}-\d{2}-\d{2})(?:-S(?P<score>[0-5]))?$")
_TIME_ALBUM = re.compile(r"^(?P<base>\d{4}-\d{4}(?:-\d+)?)(?:-S(?P<score>[0-5]))?$")


@dataclass(frozen=True, slots=True)
class AlbumRename:
    work_dir: Path
    old_date_dir: Path
    date_dir: Path
    score: int


def date_album_path(auto_root: Path, date_name: str) -> Path:
    """Prefer an existing scored container for newly created time albums."""
    root = auto_root.expanduser().resolve()
    candidates: list[tuple[int, Path]] = []
    try:
        entries = tuple(root.iterdir())
    except FileNotFoundError:
        entries = ()
    except OSError:
        return root / date_name
    for entry in entries:
        match = _DATE_ALBUM.fullmatch(entry.name)
        if (
            match is None
            or match.group("base") != date_name
            or not entry.is_dir()
            or entry.is_symlink()
        ):
            continue
        score = int(match.group("score")) if match.group("score") else -1
        candidates.append((score, entry.resolve()))
    return max(candidates, default=(-2, root / date_name), key=lambda item: item[0])[1]


def label_sunset_album(
    work_dir: Path,
    auto_root: Path,
    score: int,
) -> AlbumRename | None:
    """Apply ``-Sx`` to one time album and its date container."""
    if type(score) is not int or not 0 <= score <= 5:
        raise ValueError("晚霞评分必须是 0 到 5 之间的整数")
    source = work_dir.expanduser()
    root = auto_root.expanduser().resolve()
    if source.is_symlink() or source.parent.is_symlink():
        return None
    source = source.resolve()
    try:
        relative = source.relative_to(root)
    except ValueError:
        return None
    if len(relative.parts) != 2 or not source.is_dir():
        return None
    date_match = _DATE_ALBUM.fullmatch(source.parent.name)
    time_match = _TIME_ALBUM.fullmatch(source.name)
    if date_match is None or time_match is None:
        return None

    old_date_dir = source.parent
    time_target = old_date_dir / f"{time_match.group('base')}-S{score}"
    try:
        if source != time_target:
            _require_available(time_target)
            source.rename(time_target)
        date_score = _highest_child_score(old_date_dir, score)
        date_target = old_date_dir.with_name(
            f"{date_match.group('base')}-S{date_score}"
        )
        if old_date_dir != date_target:
            if date_target.exists():
                _merge_directories(old_date_dir, date_target)
            else:
                old_date_dir.rename(date_target)
    except OSError as exc:
        raise TaskError(f"无法标记晚霞相册目录：{exc}") from exc
    return AlbumRename(
        date_target / time_target.name,
        old_date_dir,
        date_target,
        score,
    )


def rewrite_eternal_album_paths(
    state_dir: Path,
    queue_dir: Path,
    old_date_dir: Path,
    date_dir: Path,
) -> int:
    """Rewrite queued eternal batch paths after their date directory moves."""
    if old_date_dir == date_dir:
        return 0
    documents = [
        *state_dir.glob("archive.*.yaml"),
        *queue_dir.glob("*.ready.yaml"),
        *queue_dir.glob("*.failed.yaml"),
    ]
    changed = 0
    for path in documents:
        try:
            data = load_yaml(path)
        except (OSError, ConfigError) as exc:
            raise TaskError(f"无法更新永续相册路径 {path}：{exc}") from exc
        value = data.get("batch_dir")
        if not isinstance(value, str) or not value:
            continue
        batch_dir = Path(value).expanduser().resolve()
        try:
            relative = batch_dir.relative_to(old_date_dir)
        except ValueError:
            continue
        data["batch_dir"] = str(date_dir / relative)
        save_yaml(path, data)
        changed += 1
    return changed


def _highest_child_score(directory: Path, current: int) -> int:
    scores = [current]
    for child in directory.iterdir():
        if not child.is_dir() or child.is_symlink():
            continue
        match = _TIME_ALBUM.fullmatch(child.name)
        if match is not None and match.group("score") is not None:
            scores.append(int(match.group("score")))
    return max(scores)


def _require_available(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise TaskError(f"晚霞相册目标目录已存在：{path}")


def _merge_directories(source: Path, target: Path) -> None:
    if not target.is_dir() or target.is_symlink():
        raise TaskError(f"晚霞日期目录目标不安全：{target}")
    entries = tuple(source.iterdir())
    for entry in entries:
        _require_available(target / entry.name)
    for entry in entries:
        entry.rename(target / entry.name)
    source.rmdir()
