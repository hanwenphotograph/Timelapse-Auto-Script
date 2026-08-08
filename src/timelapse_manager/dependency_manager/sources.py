"""Git repositories and selectable update branches for owned dependencies."""

from __future__ import annotations

from collections.abc import Callable
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from urllib.parse import quote

from timelapse_manager.dependency_manager.models import DependencyStatus


OpenUrl = Callable[..., object]


@dataclass(frozen=True)
class SourceRepository:
    url: str
    default_branch: str

    def install_url(self, branch: str | None = None) -> str:
        selected = validate_branch(branch or self.default_branch)
        encoded = quote(selected, safe="/._-")
        return f"{self.url.removesuffix('.git')}/archive/refs/heads/{encoded}.tar.gz"

    @property
    def github_slug(self) -> str:
        prefix = "https://github.com/"
        if not self.url.startswith(prefix):
            raise ValueError(f"不支持的源码仓库：{self.url}")
        return self.url[len(prefix) :].removesuffix(".git")


SOURCE_REPOSITORIES = {
    "camera": SourceRepository(
        "https://github.com/hanwenphotograph/Camera-Timelapse-Controller.git",
        "main",
    ),
    "bracketlapse": SourceRepository(
        "https://github.com/hanwenphotograph/Bracketlapse.git",
        "master",
    ),
    "sunsetscore": SourceRepository(
        "https://github.com/hanwenphotograph/Sunset-Score.git",
        "main",
    ),
}


def inspect_remote_branches(
    identifier: str,
    *,
    timeout: float = 10.0,
    open_url: OpenUrl = urllib.request.urlopen,
) -> tuple[str, ...]:
    source = SOURCE_REPOSITORIES.get(identifier)
    if source is None:
        return ()
    try:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{source.github_slug}/branches?per_page=100",
            headers={"Accept": "application/vnd.github+json"},
        )
        with open_url(request, timeout=timeout) as response:  # type: ignore[attr-defined]
            document = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return (source.default_branch,)
    if not isinstance(document, list):
        return (source.default_branch,)
    branches = {
        name
        for item in document
        if isinstance(item, dict) and isinstance(name := item.get("name"), str) and name
    }
    branches.add(source.default_branch)
    return (
        source.default_branch,
        *sorted(branch for branch in branches if branch != source.default_branch),
    )


def package_install_url(identifier: str, branch: str | None = None) -> str | None:
    source = SOURCE_REPOSITORIES.get(identifier)
    return source.install_url(branch) if source is not None else None


def validate_branch(value: str) -> str:
    branch = value.strip()
    forbidden = ("..", "@{", "\\", "~", "^", ":", "?", "*", "[")
    if (
        not branch
        or branch.startswith(("/", "."))
        or branch.endswith(("/", ".", ".lock"))
        or any(token in branch for token in forbidden)
        or any(character.isspace() or ord(character) < 32 for character in branch)
    ):
        raise ValueError(f"无效的 Git 分支名称：{value!r}")
    return branch


PACKAGE_URLS = {
    identifier: source.install_url()
    for identifier, source in SOURCE_REPOSITORIES.items()
}


def attach_source_branches(
    status: DependencyStatus,
    branches: dict[str, tuple[str, ...]],
) -> DependencyStatus:
    available = branches.get(status.spec.identifier, ())
    return replace(
        status,
        available_branches=available,
        selected_branch=available[0] if available else None,
    )
