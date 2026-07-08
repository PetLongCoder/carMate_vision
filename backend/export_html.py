"""
将 OpenAPI JSON 文件导出为独立的 HTML 接口文档

用法: cd backend && python export_html.py

输出:
  - docs/api_main.html      (主 API 交互式文档)
  - docs/api_inference.html (推理服务交互式文档)

生成的 HTML 是自包含的，直接用浏览器打开即可，也可以发给别人。
"""

import json
from pathlib import Path

docs_dir = Path(__file__).parent.parent / "docs"

for json_name, html_name, title in [
    ("openapi_main.json", "api_main.html", "CarMate 主 API — 认证、车牌、手势、告警"),
    ("openapi_inference.json", "api_inference.html", "CarMate 推理服务 — 交警手势识别"),
]:
    spec_path = docs_dir / json_name
    if not spec_path.exists():
        print(f"⚠️  跳过: {json_name} 不存在，请先运行 export_openapi.py")
        continue

    # 把 JSON 内嵌进 HTML，避免跨域问题
    spec_json = spec_path.read_text(encoding="utf-8")

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    html {{ font-family: sans-serif; }}
    body {{ margin: 0; }}
    .topbar {{ display: none; }}
    .info {{ margin: 20px 0; }}
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" crossorigin></script>
  <script>
    SwaggerUIBundle({{
      spec: {spec_json},
      dom_id: "#swagger-ui",
      deepLinking: true,
      defaultModelsExpandDepth: -1,
      docExpansion: "list",
    }});
  </script>
</body>
</html>'''

    out_path = docs_dir / html_name
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ {title} -> {out_path}")

print("\n📖 完成！用浏览器直接打开 docs/ 下的 .html 文件即可查看交互式接口文档。")
print("   也可以把 .html 文件发给别人（只需一个文件，无需网络服务）。")
