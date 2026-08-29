"""仓库注册表：按名称访问各集合的 Repository。"""
from __future__ import annotations

from typing import Dict

from repositories.base import BaseRepository


class Registry:
    def __init__(self) -> None:
        self._repos: Dict[str, BaseRepository] = {}

    def register(self, name: str, repo: BaseRepository) -> None:
        self._repos[name] = repo

    def __getattr__(self, name: str) -> BaseRepository:
        try:
            return self._repos[name]
        except KeyError:
            raise AttributeError(f"未注册的仓库: {name}")

    def names(self) -> list:
        return list(self._repos.keys())
