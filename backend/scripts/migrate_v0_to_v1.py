"""v0 → v1 数据迁移：把旧的单文件 data.json 拆分为 data/ 目录下的分集合文件。

用法（在 backend 目录下）：
    python scripts/migrate_v0_to_v1.py

迁移内容：
- users      -> data/users.json
- reports    -> data/calculation_reports.json
- orders     -> data/orders.json
- trades     -> data/trades.json
- points     -> data/points_ledger.json
- 每条记录补 created_at / updated_at（缺失时以 created_at 回填）
- 旧 data.json 备份到 data/v0_data.json.bak（新存储层会忽略该文件）
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

V0_FILE = os.path.join(BACKEND_DIR, "data.json")
DATA_DIR = os.path.join(BACKEND_DIR, "data")

# 旧集合名 -> 新文件名（collection）
COLLECTION_MAP = {
    "users": "users",
    "reports": "calculation_reports",
    "orders": "orders",
    "trades": "trades",
    "points": "points_ledger",
}


def main() -> None:
    if not os.path.exists(V0_FILE):
        print("未找到 data.json，无需迁移。")
        return

    with open(V0_FILE, "r", encoding="utf-8") as f:
        old = json.load(f)

    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.utcnow().isoformat()

    for old_name, new_name in COLLECTION_MAP.items():
        target = os.path.join(DATA_DIR, f"{new_name}.json")
        if os.path.exists(target):
            print(f"跳过 {new_name}.json（已存在）")
            continue
        records = old.get(old_name, {})
        items = {}
        for rid, rec in records.items():
            rec = dict(rec)
            rec["id"] = rec.get("id", rid)
            rec.setdefault("created_at", now)
            rec.setdefault("updated_at", rec["created_at"])
            items[rid] = rec
        doc = {
            "schema_version": 1,
            "collection": new_name,
            "updated_at": now,
            "items": items,
        }
        with open(target, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"已迁移 {old_name} -> {new_name}.json（{len(items)} 条）")

    backup = os.path.join(DATA_DIR, "v0_data.json.bak")
    shutil.move(V0_FILE, backup)
    print(f"旧 data.json 已备份至 {backup}")


if __name__ == "__main__":
    main()
