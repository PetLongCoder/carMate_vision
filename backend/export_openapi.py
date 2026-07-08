"""
导出 FastAPI OpenAPI Schema 为 JSON 文件

用法: cd backend && python export_openapi.py

输出:
  - docs/openapi_main.json      (主 API: 认证、车牌、手势、告警等)
  - docs/openapi_inference.json (推理服务: 交警手势姿势估计)
"""

import json
import sys
import types
from pathlib import Path

docs_dir = Path(__file__).parent.parent / "docs"
docs_dir.mkdir(parents=True, exist_ok=True)

# ── 1. 提前 mock 需要在启动时加载模型的服务 ──
def _patch_service_modules():
    """
    在 app 导入之前，将需要 GPU/CV 模型的服务模块替换为 mock，
    避免 HandTracker() 和 hyperlpr3 在导入阶段就加载模型。
    """
    # mock plate_recognition（需要 hyperlpr3 + ultralytics）
    plate_mock = types.ModuleType("app.services.plate_recognition")
    plate_mock.recognize_plates = lambda *a, **kw: []  # type: ignore
    plate_mock.recognize_plates_from_video = lambda *a, **kw: []  # type: ignore
    sys.modules["app.services.plate_recognition"] = plate_mock

    # mock hand_tracker（需要 mediapipe + cv2）
    ht_mock = types.ModuleType("app.services.hand_tracker")
    ht_mock.HandTracker = type("HandTracker", (), {  # type: ignore
        "process_frame": lambda self, img: ("unknown", 0.0, None),
    })
    sys.modules["app.services.hand_tracker"] = ht_mock

    # 占位 cv2 / mediapipe / hyperlpr3 / ultralytics
    for mod in ["cv2", "mediapipe", "hyperlpr3", "ultralytics"]:
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

_patch_service_modules()

# ── 2. 推理服务 (server.py) ──
# 清除 mocks 让 server.py 用自己的真实导入
for _m in ["cv2", "mediapipe"]:
    sys.modules.pop(_m, None)

try:
    from server import app as server_app
    server_schema = server_app.openapi()
    with open(docs_dir / "openapi_inference.json", "w", encoding="utf-8") as f:
        json.dump(server_schema, f, ensure_ascii=False, indent=2)
    print(f"✅ 推理服务 OpenAPI ({len(server_schema['paths'])} 个端点) -> {docs_dir / 'openapi_inference.json'}")
except Exception as e:
    print(f"⚠️  推理服务导出失败: {e}")

# ── 3. 主 API (app/main.py) ──
# 重新安装 service mock（server 的导入可能覆盖了部分 mock）
_patch_service_modules()

try:
    from app.main import app as main_app
    main_schema = main_app.openapi()
    with open(docs_dir / "openapi_main.json", "w", encoding="utf-8") as f:
        json.dump(main_schema, f, ensure_ascii=False, indent=2)
    print(f"✅ 主服务 OpenAPI ({len(main_schema['paths'])} 个端点) -> {docs_dir / 'openapi_main.json'}")
except Exception as e:
    print(f"❌ 主服务代码导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n📖 导出完成！在 VS Code 中右键 docs/openapi_*.json → OpenAPI Editor")
