"""Repository 抽象基类：模板方法统一时间戳填充 / 校验 / 落盘。

子类只需声明 collection / record_model / append_only 三个配置，
或直接在构造时传入（见 JsonRepository）。
"""
from __future__ import annotations

from abc import ABC
from typing import Any, Generic, List, Optional, TypeVar

from schemas.common import _now, _uid
from storage.json_store import JsonStore

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    collection: str          # 存储文件名（如 "users" / "points_ledger"）
    record_model: type       # 对应 Pydantic 模型
    append_only: bool = False  # 追加型集合禁止 update / delete

    def __init__(self, store: JsonStore):
        self.store = store

    # -- 读 ---------------------------------------------------------------
    def get(self, record_id: str) -> Optional[T]:
        raw = self.store.read_item(self.collection, record_id)
        return self.record_model(**raw) if raw else None

    def list(self, **filters: Any) -> List[T]:
        items = [self.record_model(**r) for r in self.store.list_items(self.collection)]
        if filters:
            items = [i for i in items
                     if all(getattr(i, k, None) == v for k, v in filters.items())]
        return items

    def count(self) -> int:
        return len(self.store.all_items(self.collection))

    # -- 写 ---------------------------------------------------------------
    def create(self, record: T) -> T:
        data = record.model_dump()
        data.setdefault("id", _uid())
        data["created_at"] = data.get("created_at") or _now()
        data["updated_at"] = _now()
        self.store.write_item(self.collection, data["id"], data)
        return self.record_model(**data)

    def update(self, record_id: str, changes: dict) -> Optional[T]:
        if self.append_only:
            raise TypeError(f"{self.collection} 为追加型集合，不允许 update")
        raw = self.store.read_item(self.collection, record_id)
        if raw is None:
            return None
        changes = dict(changes)
        changes["updated_at"] = _now()
        raw.update(changes)
        self.store.write_item(self.collection, record_id, raw)
        return self.record_model(**raw)

    def delete(self, record_id: str) -> bool:
        if self.append_only:
            raise TypeError(f"{self.collection} 为追加型集合，不允许 delete")
        return self.store.delete_item(self.collection, record_id)
