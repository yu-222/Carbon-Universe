"""JSON 文件 Repository 实现。

配置化构造：JsonRepository(store, Model, collection="xxx", append_only=True)
"""
from __future__ import annotations

from typing import Generic, TypeVar

from repositories.base import BaseRepository
from storage.json_store import JsonStore

T = TypeVar("T")


class JsonRepository(BaseRepository[T], Generic[T]):
    def __init__(self, store: JsonStore, record_model: type,
                 collection: str, append_only: bool = False):
        self.store = store
        self.record_model = record_model
        self.collection = collection
        self.append_only = append_only
