"""车牌记录存储服务 — 将识别结果中的每个车牌写入 plate_records 表。"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.db_models import PlateRecord


def save_plate_records(
    db: Session,
    *,
    history_record_id: int,
    user_id: int | None,
    session_id: str | None,
    plates: list[dict[str, Any]],
    source_type: str | None,
) -> list[PlateRecord]:
    """
    将识别结果中的车牌列表存入 plate_records 表。

    每辆车牌写入一行 PlateRecord。调用方负责最终 db.commit()。
    同一个 session_id 的多次调用会先删除旧记录再写入（用于追踪更新场景）。
    """
    # 追踪更新场景: 先清除该 session 的旧记录, 再写入新的
    if session_id:
        db.query(PlateRecord).filter(
            PlateRecord.session_id == session_id
        ).delete(synchronize_session=False)

    created: list[PlateRecord] = []
    for plate in plates:
        plate_no = plate.get("plateNo") or plate.get("plate_no")
        if not plate_no:
            continue

        rec = PlateRecord(
            history_record_id=history_record_id,
            session_id=session_id,
            user_id=user_id,
            plate_no=plate_no,
            color=plate.get("color"),
            vehicle_type=plate.get("vehicleType"),
            confidence=plate.get("confidence"),
            first_seen=plate.get("firstSeen"),
            last_seen=plate.get("lastSeen"),
            appearances=plate.get("appearances", 1),
            source_type=source_type,
        )
        db.add(rec)
        created.append(rec)

    return created


def extract_plates_from_result(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """从识别结果 dict 中提取 plates 列表。

    支持多种格式:
    - result["plates"] (主要格式)
    - result["items"]  (备选格式)
    - result 本身就是 list
    """
    if not result:
        return []
    if isinstance(result, list):
        return result
    plates = result.get("plates") or result.get("items") or []
    return plates if isinstance(plates, list) else []
