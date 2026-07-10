"""一次性脚本: 将已有 history_records 中的车牌数据回填到 plate_records。

用法:
  cd backend
  python -m scripts.backfill_plate_records
"""

import json
import os
import sys

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.models.db_models import HistoryRecord, PlateRecord
from app.services.plate_record_service import save_plate_records


def backfill():
    db = SessionLocal()
    try:
        records = (
            db.query(HistoryRecord)
            .filter(
                HistoryRecord.type == "plate",
                HistoryRecord.result_json.isnot(None),
            )
            .all()
        )

        total = 0
        skipped = 0
        for record in records:
            # 跳过已回填的
            existing_count = db.query(PlateRecord).filter(
                PlateRecord.history_record_id == record.id
            ).count()
            if existing_count > 0:
                skipped += 1
                continue

            try:
                result = json.loads(record.result_json)
            except (json.JSONDecodeError, TypeError):
                continue

            plates = result.get("plates") or result.get("items") or []
            if not plates:
                continue

            source_type = result.get("sourceType")
            save_plate_records(
                db,
                history_record_id=record.id,
                user_id=record.user_id,
                session_id=record.session_id,
                plates=plates,
                source_type=source_type,
            )
            total += 1

            if total % 100 == 0:
                db.commit()  # 分批提交

        db.commit()
        print(
            f"回填完成: {total} 条历史记录写入 plate_records, "
            f"{skipped} 条已存在跳过"
        )
    finally:
        db.close()


if __name__ == "__main__":
    backfill()
