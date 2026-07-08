# CarMate API 接口文档 — 使用指南

## 概述

本项目使用 **FastAPI** 构建后端，OpenAPI 3.1 规格自动生成。两条命令即可导出接口文档。

### 两个服务

| 服务 | 应用入口 | 端点数 |
|---|---|---|
| **主 API** — 认证 / 车牌 / 手势 / 告警 / 历史 / 统计 | `backend/app/main.py` | 16 |
| **推理服务** — 交警手势识别（含 GPU 推理） | `backend/server.py` | 8 |

---

## 一、生成接口文档

### 第一步：导出 OpenAPI JSON

```powershell
cd E:\carMate_vision\backend
python export_openapi.py
```

> 输出：`docs/openapi_main.json`、`docs/openapi_inference.json`

### 第二步：生成浏览器可打开的 HTML

```powershell
cd E:\carMate_vision\backend
python export_html.py
```

> 输出：`docs/api_main.html`、`docs/api_inference.html`

### 一键执行（可选）

```powershell
cd E:\carMate_vision\backend
python export_openapi.py && python export_html.py
```

---

## 二、查看接口文档（三种方式）

### 方式 1：浏览器打开（最简单）

直接双击 `.html` 文件：

```
📁 docs/
  ├── api_main.html       ← 双击打开，交互式文档
  └── api_inference.html  ← 双击打开，交互式文档
```

特点：
- 可折叠/展开每个接口
- 点击 **Try it out** → 填写参数 → **Execute**，直接调用后端
- 发给其他人无需安装任何工具

### 方式 2：VS Code 内置预览

1. 在 VS Code 中打开 `docs/openapi_main.json`
2. 按 `Ctrl+Shift+P` → 输入 `OpenAPI Show Preview` → 回车

特点：
- 使用 Swagger UI 渲染
- 在编辑器内分屏查看

### 方式 3：FastAPI 自带的 Swagger 文档

启动后端后，浏览器访问：

```
http://127.0.0.1:8000/docs        # Swagger UI（可交互）
http://127.0.0.1:8000/redoc       # ReDoc（只读，适合截图）
```

---

## 三、42Crunch VS Code 插件使用

已安装插件：**42Crunch vscode-openapi**

### 打开侧边栏

VS Code 左侧活动栏找到 **OpenAPI** 图标（`{}`），点击后显示：

| 功能 | 说明 |
|---|---|
| **Navigator** | 树形展示所有接口，按 Tag 分组，点击跳转 |
| **Try It** | 直接发 HTTP 请求，无需 Postman |
| **Security Audit** | 扫描 API 安全问题 |

### 常用快捷键

| 操作 | 快捷键 / 命令 |
|---|---|
| 预览接口文档 | `Ctrl+Shift+P` → `OpenAPI: Show Preview` |
| 跳转到路径定义 | `Ctrl+Shift+P` → `OpenAPI: Go to Path` |
| 安全审计 | 右键 `.json` 文件 → `OpenAPI: Security Audit` |

---

## 四、导出为其他格式

### 导出为 PDF

1. 浏览器打开 `api_main.html`
2. `Ctrl+P` → 目标选择 "另存为 PDF"
3. 保存

### 导出为 Markdown（使用 widdershins）

```powershell
npm install -g widdershins
widdershins docs/openapi_main.json -o docs/api_main.md
```

---

## 五、常见问题

**Q: 为什么文档里请求参数/响应是空的？**

A: 部分接口（告警、历史、统计）目前在代码中使用简化的返回参数，未使用 Pydantic model。可以给这些接口替换为 `response_model=` 来丰富文档。

**Q: 接口变更后文档怎么更新？**

A: 重新运行 `python backend/export_openapi.py && python backend/export_html.py` 即可。

**Q: 后端没启动也能生成文档吗？**

A: 可以。`export_openapi.py` 直接从 Python 代码导入 FastAPI app 生成 schema，无需启动服务。
