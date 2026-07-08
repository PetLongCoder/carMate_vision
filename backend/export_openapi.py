"""
导出 FastAPI OpenAPI Schema 为 JSON 文件

用法: cd backend && python export_openapi.py

输出:
  - docs/openapi_main.json      (主 API: 认证、车牌、手势、告警等)
"""

import json
import sys
import types
from pathlib import Path

docs_dir = Path(__file__).parent.parent / "docs"
docs_dir.mkdir(parents=True, exist_ok=True)

# ── 提前 mock 需要在启动时加载模型的服务 ──
def _patch_service_modules():
    """将需要 GPU/CV 模型的服务模块替换为 mock，避免导入阶段加载模型。"""
    # mock plate_recognition（需要 hyperlpr3 + ultralytics）
    plate_mock = types.ModuleType("app.services.plate_recognition")
    plate_mock.recognize_plates = lambda *a, **kw: []
    plate_mock.recognize_plates_from_video = lambda *a, **kw: []
    sys.modules["app.services.plate_recognition"] = plate_mock

    # mock hand_tracker（需要 mediapipe + cv2）
    ht_mock = types.ModuleType("app.services.hand_tracker")
    ht_mock.HandTracker = type("HandTracker", (), {
        "process_frame": lambda self, img: ("unknown", 0.0, None),
    })
    sys.modules["app.services.hand_tracker"] = ht_mock

    # mock police_gesture_service（需要 ctpgr + cv2 + torch）
    pg_mock = types.ModuleType("app.services.police_gesture_service")
    pg_mock.GESTURE_NAMES_CN = ["无手势"] * 9
    pg_mock.VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".webm", ".mkv")
    pg_mock.get_torch_device_info = lambda: {"device": "cpu"}
    pg_mock.is_model_loaded = lambda: False
    pg_mock.preload_model = lambda: None
    pg_mock.process_police_gesture_image = lambda *a, **kw: {"code": 200}
    pg_mock.process_police_gesture_video = lambda *a, **kw: {"code": 200}
    pg_mock.generate_police_gesture_video_stream = lambda *a, **kw: iter([])
    pg_mock.process_stream_frame = lambda *a, **kw: {"code": 200}
    pg_mock.reset_stream_state = lambda *a, **kw: None
    pg_mock.remove_files = lambda *a: None
    pg_mock.transcode_browser_preview = lambda *a: None
    sys.modules["app.services.police_gesture_service"] = pg_mock

    # 占位 cv2 / mediapipe / hyperlpr3 / ultralytics
    for mod in ["cv2", "mediapipe", "hyperlpr3", "ultralytics"]:
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

_patch_service_modules()

# ── 主 API (app/main.py) ──
try:
    from app.main import app as main_app
    main_schema = main_app.openapi()
    with open(docs_dir / "openapi_main.json", "w", encoding="utf-8") as f:
        json.dump(main_schema, f, ensure_ascii=False, indent=2)
    print(f"[OK] 主服务 OpenAPI ({len(main_schema['paths'])} 个端点) -> {docs_dir / 'openapi_main.json'}")
except Exception as e:
    print(f"[ERROR] 主服务代码导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n导出完成！在 VS Code 中右键 docs/openapi_*.json -> OpenAPI Editor")
