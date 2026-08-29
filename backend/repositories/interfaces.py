"""统一 Repository 接口（Protocol）。

业务层（路由 / Agent / Service）只依赖本接口，不关心底层是 JSON 文件
还是 SQL 数据库。未来实现 SqlRepository 满足同一协议即可无痛替换。
"""
from __future__ import annotations

from typing import Any, List, Optional, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class Repository(Protocol[T]):
    """统一读写接口：所有集合仓库必须实现。"""

    def get(self, record_id: str) -> Optional[T]:
        """按稳定 ID 取单条记录，不存在返回 None。"""
        ...

    def list(self, **filters: Any) -> List[T]:
        """列出全部记录；传 keyword 时按字段等值过滤。"""
        ...

    def create(self, record: T) -> T:
        """新增记录：自动补 id / created_at / updated_at 并落盘。"""
        ...

    def update(self, record_id: str, changes: dict) -> Optional[T]:
        """按 ID 部分更新，自动刷新 updated_at；追加型集合会抛错。"""
        ...

    def delete(self, record_id: str) -> bool:
        """按 ID 删除，返回是否删除成功；追加型集合会抛错。"""
        ...

    def count(self) -> int:
        """记录总数。"""
        ...
