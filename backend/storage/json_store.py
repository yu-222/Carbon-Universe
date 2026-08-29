"""本地 JSON 存储层：每集合一个文件，加载时校验，写入原子替换。

设计要点（对应 plan.md 4.1）：
- 一集合一文件：data/<collection>.json
- 文件头带 schema_version / collection / updated_at，items 以稳定 ID 为键
- 写入时先写临时文件再 os.replace，避免中途崩溃损坏数据
- 每次写入用 Pydantic 校验记录，坏数据不落盘
- 每集合独立线程锁，写操作串行化
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

_SCHEMA_VERSION = 1


class JsonStore:
    def __init__(self, data_dir: str, schemas: Dict[str, type]):
        self.data_dir = data_dir
        self.schemas = schemas                      # {collection: Pydantic model}
        self._locks: Dict[str, threading.RLock] = {}
        self._cache: Dict[str, Dict[str, dict]] = {}
        os.makedirs(data_dir, exist_ok=True)
        self.load()

    # -- 内部工具 ----------------------------------------------------------
    def _lock(self, collection: str) -> threading.RLock:
        return self._locks.setdefault(collection, threading.RLock())

    def _path(self, collection: str) -> str:
        return os.path.join(self.data_dir, f"{collection}.json")

    # -- 加载：启动时校验，坏数据直接报错而不是静默进入 ---------------------
    def load(self) -> None:
        for collection, model in self.schemas.items():
            path = self._path(collection)
            items: Dict[str, dict] = {}
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        doc = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    raise RuntimeError(f"读取数据文件失败: {path}: {e}")
                for rid, raw in doc.get("items", {}).items():
                    # 校验不合法即拒绝启动，防止坏数据被后续逻辑复用
                    try:
                        model.model_validate(raw)
                    except Exception as e:
                        raise RuntimeError(f"数据校验失败 {path} 记录 {rid}: {e}")
                    items[rid] = raw
            self._cache[collection] = items

    # -- 读取 --------------------------------------------------------------
    def read_item(self, collection: str, record_id: str) -> Optional[dict]:
        return self._cache[collection].get(record_id)

    def list_items(self, collection: str) -> List[dict]:
        return list(self._cache[collection].values())

    def all_items(self, collection: str) -> Dict[str, dict]:
        return self._cache[collection]

    # -- 写入 --------------------------------------------------------------
    def write_item(self, collection: str, record_id: str, record: dict) -> None:
        self.schemas[collection].model_validate(record)  # 写入前校验
        with self._lock(collection):
            self._cache[collection][record_id] = record
            self._flush(collection)

    def delete_item(self, collection: str, record_id: str) -> bool:
        with self._lock(collection):
            if record_id not in self._cache[collection]:
                return False
            del self._cache[collection][record_id]
            self._flush(collection)
            return True

    def _flush(self, collection: str) -> None:
        """原子落盘：临时文件 + os.replace。"""
        path = self._path(collection)
        doc = {
            "schema_version": _SCHEMA_VERSION,
            "collection": collection,
            "updated_at": datetime.utcnow().isoformat(),
            "items": self._cache[collection],
        }
        fd, tmp = tempfile.mkstemp(dir=self.data_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
