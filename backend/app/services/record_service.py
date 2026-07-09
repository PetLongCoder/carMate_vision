"""识别记录服务（写入 history_records + recognition_records）。"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.db_models import HistoryRecord, RecognitionRecord, User

TYPE_LABELS: dict[str, str] = {
    "plate": "车牌识别",
    "police_gesture": "交警手势",
    "driver_gesture": "车主手势",
}


def build_plate_summary(plates: list[dict[str, Any]]) -> str:
    if not plates:
        return "未识别到车牌"
    names = [p.get("plateNo") or p.get("plate_no") or "未知" for p in plates]
    return "、".join(names[:5])


def build_gesture_summary(data: dict[str, Any]) -> str:
    gesture = data.get("gesture") or data.get("gesture_name")
    if gesture:
        conf = data.get("confidence")
        if conf is not None:
            return f"{gesture} ({float(conf) * 100:.0f}%)"
        return str(gesture)
    return "未识别"


def extract_confidence(result: dict[str, Any]) -> float | None:
    if "confidence" in result and result["confidence"] is not None:
        return float(result["confidence"])
    plates = result.get("plates")
    if isinstance(plates, list) and plates:
        first = plates[0]
        if isinstance(first, dict) and first.get("confidence") is not None:
            return float(first["confidence"])
    return None


def log_recognition(
    db: Session,
    *,
    record_type: str,
    success: bool,
    summary: str,
    result: dict[str, Any] | list[Any] | None = None,
    file_name: str | None = None,
    source_type: str | None = None,
    session_id: str | None = None,
    user: User | None = None,
) -> HistoryRecord:
    payload: dict[str, Any] = {}
    if isinstance(result, dict):
        payload = dict(result)
    elif isinstance(result, list):
        payload = {"items": result}
    # 剥离逐帧数据（太大，TEXT存不下，历史记录也不需要）
    payload.pop("frames", None)
    payload.pop("segments", None)
    if file_name:
        payload["fileName"] = file_name
    if source_type:
        payload["sourceType"] = source_type
    if session_id:
        payload["sessionId"] = session_id
    payload["success"] = success
    if summary:
        payload["summary"] = summary

    user_id = user.id if user else None
    record = HistoryRecord(
        user_id=user_id,
        type=record_type,
        session_id=session_id,
        image_url="",
        result_json=json.dumps(payload, ensure_ascii=False) if payload else None,
    )
    db.add(record)
    db.add(
        RecognitionRecord(
            user_id=user_id,
            type=record_type,
            result_summary=summary[:255] if summary else None,
            confidence=extract_confidence(payload),
            success=success,
        )
    )
    db.commit()
    return record


def update_recognition_by_session(
    db: Session,
    session_id: str,
    final_result: dict[str, Any],
    success: bool,
    summary: str,
) -> HistoryRecord | None:
    """根据 session_id 更新追踪会话的历史记录，写入最终车牌结果。"""
    record = db.query(HistoryRecord).filter(
        HistoryRecord.session_id == session_id
    ).first()
    if record is None:
        return None

    existing: dict[str, Any] = {}
    if record.result_json:
        try:
            existing = json.loads(record.result_json)
        except json.JSONDecodeError:
            existing = {}

    existing.update(final_result)
    # 剥离逐帧数据（TEXT存不下）
    existing.pop("frames", None)
    existing.pop("segments", None)
    existing["success"] = success
    existing["summary"] = summary
    record.result_json = json.dumps(existing, ensure_ascii=False)

    db.add(
        RecognitionRecord(
            user_id=record.user_id,
            type=record.type,
            result_summary=summary[:255] if summary else None,
            confidence=extract_confidence(final_result),
            success=success,
        )
    )
    db.commit()
    return record


def history_record_to_dict(record: HistoryRecord) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if record.result_json:
        try:
            parsed = json.loads(record.result_json)
            result = parsed if isinstance(parsed, dict) else {"items": parsed}
        except json.JSONDecodeError:
            result = {"raw": record.result_json}

    summary = result.get("summary")
    if not summary and record.type == "plate":
        plates = result.get("plates")
        if isinstance(plates, list):
            summary = build_plate_summary(plates)
    if not summary:
        summary = result.get("gesture") or result.get("plateNo")

    success = result.get("success")
    if success is None:
        success = True

    return {
        "id": record.id,
        "type": record.type,
        "module_label": TYPE_LABELS.get(record.type, record.type),
        "source_type": result.get("sourceType"),
        "source_label": {"image": "图片", "video": "视频", "track": "视频追踪"}.get(
            result.get("sourceType") or "", result.get("sourceType") or ""
        ),
        "file_name": result.get("fileName"),
        "success": bool(success),
        "summary": summary,
        "image": record.image_url or "",
        "result": result,
        "createdAt": record.created_at.isoformat() if record.created_at else None,
    }
