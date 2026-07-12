# CarMate AlertAgent 告警智能体系统 — 实现报告

> **项目名称**：CarMate 车载视觉系统 — 告警智能体（AlertAgent）
> **实现日期**：2026年7月12日
> **分支**：zbl
> **作者**：PetLongCoder

---

## 一、系统概述

AlertAgent 是 CarMate 车载视觉系统的智能告警子系统，具备以下核心能力：

| 能力 | 说明 |
|------|------|
| **异常事件感知** | 自动监测车牌识别失败、手势置信度偏低、未授权访问等系统异常 |
| **告警级别自主决策** | 基于规则引擎 + 滑动窗口计数器，自动判定提示/警告/严重 |
| **LLM 摘要生成** | 通过 DeepSeek API 自动生成自然语言告警摘要（含异常类型、影响范围、建议处置措施） |
| **多渠道通知推送** | 支持 WebSocket 实时推送（前端） + 飞书群机器人 Webhook |
| **告警可视化** | 仪表盘（ECharts 图表）、时间线、事件回放、原因分析 |

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                       AlertAgent 核心                        │
│                                                             │
│  ┌───────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ EventCollector │ → │ DecisionEngine│ → │ DeepSeek LLM   │  │
│  │ (事件采集器)    │   │ (告警分级引擎) │   │ (自然语言摘要)  │  │
│  └───────────────┘   └──────────────┘   └────────────────┘  │
│         ↓                                       ↓            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              NotificationDispatcher                     │  │
│  │   ┌──────────────┐   ┌───────────────┐   ┌──────────┐ │  │
│  │   │ WebSocket Push│   │ Feishu Webhook│   │ MySQL DB │ │  │
│  │   │ (前端实时推送) │   │ (飞书群机器人) │   │(告警持久化)│ │  │
│  │   └──────────────┘   └───────────────┘   └──────────┘ │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
          ↑ 事件来源（非侵入式钩子，各模块仅添加 1-2 行代码）
┌─────────────┬──────────────┬──────────────┬──────────────────┐
│ Plate       │ Police       │ Driver       │ Auth             │
│ Recognition │ Gesture      │ Gesture      │ (登录/权限)       │
│ (车牌识别)   │ (交警手势)    │ (车主手势)    │                  │
└─────────────┴──────────────┴──────────────┴──────────────────┘
```

### 事件数据流

```
1. 识别模块发生异常（如 HyperLPR3 模型加载失败）
2. 在现有 except 块旁调用 event_collector.collect(AnomalyEvent(...))
3. AlertAgent.process_event() 执行：
   a. DecisionEngine 决策告警级别
   b. 防抖检查（同类事件 60 秒内不重复告警）
   c. DeepSeek LLM 生成中文告警摘要（失败则降级为模板）
   d. 写入 MySQL alert_records 表
   e. WebSocket 广播给所有已连接前端
   f. POST 飞书 Webhook 推送消息卡片
4. 前端 Zustand store 收到 WebSocket 消息 → 侧边栏徽章 +1
5. 飞书群收到消息卡片通知
```

---

## 三、文件清单

### 新建文件（后端 7 个 + 前端 4 个）

| 文件 | 功能 |
|------|------|
| `backend/app/services/alert_agent/__init__.py` | 类型定义（AnomalyEvent, AlertLevel, 中英文标签映射） |
| `backend/app/services/alert_agent/alert_agent.py` | 核心引擎（DecisionEngine + 防抖 + 持久化 + 分发调度） |
| `backend/app/services/alert_agent/llm_summary.py` | DeepSeek API 调用 + 13 种异常类型的降级模板 |
| `backend/app/services/alert_agent/event_collector.py` | 全局事件采集器单例（fire-and-forget 模式） |
| `backend/app/services/alert_agent/ws_alert_manager.py` | WebSocket 连接池管理（广播告警到所有已订阅客户端） |
| `backend/app/services/alert_agent/notification_dispatcher.py` | 多渠道通知分发（WebSocket + 飞书卡片消息） |
| `backend/app/api/v1/alert_stats.py` | 告警统计/时间线/详情/分析/批量确认 API |
| `frontend/src/pages/AlertDashboard.tsx` | ECharts 告警统计仪表盘（饼图 + 趋势图 + 柱状图） |
| `frontend/src/pages/AlertTimeline.tsx` | 告警时间线页面（按日期分组，支持筛选） |
| `frontend/src/pages/AlertDetail.tsx` | 告警详情页（摘要 + 建议措施 + 原始事件回放 + 相关告警） |
| `frontend/src/pages/AlertAnalysis.tsx` | 告警原因分析页（来源分布 + 峰值时段 + Top 异常类型排行） |

### 修改文件（后端 8 个 + 前端 6 个）

| 文件 | 修改内容 |
|------|---------|
| `backend/app/models/db_models.py` | AlertRecord 增加 7 个字段（anomaly_type, impact_scope, suggested_actions, raw_event, notified_channels, acknowledged_by, acknowledged_at） |
| `backend/app/core/config.py` | 新增 12 个配置项（LLM_API_KEY, LLM_MODEL, ALERT_FEISHU_WEBHOOK_URL 等） |
| `backend/app/core/database.py` | 新增 ensure_alert_columns() 数据库迁移函数 |
| `backend/app/main.py` | 注册 alert_stats 路由、lifecycle 中初始化 AlertAgent、/ws 端点集成 ws_alert_manager |
| `backend/app/api/v1/alerts.py` | 扩展 alert_to_dict()、acknowledge 端点增加 acknowledged_by/at |
| `backend/app/api/v1/plate.py` | 模型加载失败 + 图片解码失败 两个点添加 event_collector.collect() |
| `backend/app/api/v1/police_gesture.py` | 识别异常点添加 event_collector.collect() |
| `backend/app/api/v1/driver_gesture.py` | 模型加载失败 + 低置信度两个点添加事件采集 |
| `backend/app/api/v1/auth.py` | 密码错误 + 非管理员访问两个点添加事件采集 |
| `backend/.env.example` | 添加 LLM/飞书 配置示例 |
| `frontend/src/types/index.ts` | 扩展 Alert 接口，新增 AlertStats, AlertAnalysis 等类型 |
| `frontend/src/api/index.ts` | 新增 getAlertStats, getAlertTimeline, getAlertDetail, getAlertAnalysis 等 API 函数 |
| `frontend/src/App.tsx` | 注册 4 个新路由（仪表盘/时间线/详情/分析），普通用户可访问 |
| `frontend/src/pages/AlertCenter.tsx` | 增强表格列（异常类型）、新增批量确认、导航按钮 |
| `frontend/src/components/layout/AppLayout.tsx` | 侧边栏新增告警仪表盘/时间线/分析菜单项 |
| `frontend/src/hooks/useWebSocket.ts` | 连接成功后自动发送告警订阅消息 |

---

## 四、核心功能实现详解

### 4.1 异常事件采集（Event Collector）

**设计思路**：非侵入式 — 在每个现有模块的 `except` 块或失败判断旁边，**只添加一行调用**。

**文件**：`backend/app/services/alert_agent/event_collector.py`

```python
# 全局单例
event_collector = EventCollector()

# 在 plate.py 中（模型加载失败时）
event_collector.collect(AnomalyEvent(
    source="plate_recognition",
    anomaly_type="plate_model_load_failure",
    title="车牌识别模块加载失败",
    detail={"error": str(exc), "filename": file.filename},
    severity_hint=AlertLevel.CRITICAL,
))
```

**13 种异常类型**及其中文标签全部预定义在 `ANOMALY_TYPE_LABELS` 字典中。

---

### 4.2 告警级别自主决策（Decision Engine）

**文件**：`backend/app/services/alert_agent/alert_agent.py` 中的 `_decide_level()` 方法

**决策规则**：

| 异常类型 | 触发条件 | 告警级别 |
|---------|---------|---------|
| `*_model_failure` | 模型加载失败 | **严重 (critical)** |
| `*_recognition_failure` | 连续 ≥ 10 次 | **严重 (critical)** |
| `*_recognition_failure` | 连续 3~9 次 | 警告 (warning) |
| `*_recognition_failure` | 单次 | 提示 (info) |
| `auth_unauthorized` | 5 分钟内 ≥ 10 次 | **严重 (critical)** |
| `auth_unauthorized` | 5 分钟内 3~9 次 | 警告 (warning) |
| `auth_login_failure` | 5 分钟内 ≥ 10 次 | **严重 (critical)** |
| `auth_login_failure` | 5 分钟内 3~9 次 | 警告 (warning) |
| `*_low_confidence` | 连续 ≥ 10 次 | 警告 (warning) |
| `*_low_confidence` | 3~9 次 | 提示 (info) |
| `llm_api_*` | 连续 ≥ 3 次 | 警告 (warning) |
| `llm_api_*` | 单次 | 提示 (info) |

**防抖机制**：同类异常事件在 60 秒内不重复告警（可通过 `ALERT_MIN_INTERVAL_SECONDS` 配置）。

---

### 4.3 LLM 自然语言摘要生成

**文件**：`backend/app/services/alert_agent/llm_summary.py`

**调用链**：

```
AlertAgent.process_event()
  → generate_summary(event, level)
    → call_llm_api(prompt)        # 调用 DeepSeek API
      成功 → 解析 JSON 返回 {title, summary, impact_scope, suggested_actions}
      失败 → generate_fallback()  # 降级为预定义模板
```

**LLM 配置**（在 `.env` 中）：

```bash
LLM_ENABLED=true
LLM_API_KEY=sk-2382bcd8581a4decaf997bffb6acf872
LLM_API_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT=30
LLM_MAX_TOKENS=500
```

**Prompt 设计**：中文提示词要求 LLM 返回严格 JSON 格式的结构化告警信息。系统解析后分别提取 title、summary、impact_scope、suggested_actions 四个字段。

**降级策略**：如果 LLM API 不可用（超时/网络错误/Key 未配置），系统自动使用预定义的 13 种异常类型的中文模板生成摘要，**不影响核心告警功能**。

---

### 4.4 多渠道通知分发

**文件**：`backend/app/services/alert_agent/notification_dispatcher.py`

**WebSocket 实时推送**：
1. 前端连接 `/ws` 后自动发送 `{"type":"subscribe","channel":"alerts"}`
2. 后端 `WebSocketAlertManager` 维护所有已订阅连接池
3. 告警产生时 `broadcast_alert()` 向所有连接推送 `{"type":"alert","payload":{...}}`
4. 前端 `useWebSocket` hook 接收后调用 `addAlert()` → Zustand store → UI 自动更新

**飞书群机器人**：
- Webhook URL：`https://open.feishu.cn/open-apis/bot/v2/hook/f2026cea-209f-46e7-8243-44c318ddbe15`
- 消息格式：飞书交互式卡片 (interactive card)
- 根据告警级别显示不同颜色头部（严重=红色，警告=橙色，提示=蓝色）
- 卡片包含：异常类型、来源模块、时间、影响范围、详细摘要、建议处置措施

**通知渠道配置**：

```bash
ALERT_NOTIFICATION_ENABLED=true
ALERT_WEBSOCKET_ENABLED=true
ALERT_FEISHU_ENABLED=true
```

---

### 4.5 数据库存储

**表**：`alert_records`（在原有基础上扩展了 7 个字段）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT (PK) | 自增主键 |
| `level` | VARCHAR(20) | info / warning / critical |
| `title` | VARCHAR(200) | 告警标题 |
| `summary` | TEXT | 详细摘要（LLM 生成或模板） |
| `source` | VARCHAR(100) | 来源模块 |
| `anomaly_type` | VARCHAR(50) | 异常类型标签 |
| `impact_scope` | VARCHAR(200) | 影响范围 |
| `suggested_actions` | TEXT | 建议处置措施（JSON 数组） |
| `raw_event` | TEXT | 原始事件数据（JSON，用于事件回放） |
| `notified_channels` | VARCHAR(200) | 已通知渠道（逗号分隔） |
| `acknowledged` | BOOLEAN | 是否已确认 |
| `acknowledged_by` | VARCHAR(50) | 确认人 |
| `acknowledged_at` | DATETIME | 确认时间 |
| `created_at` | DATETIME | 创建时间 |

数据库迁移在应用启动时自动执行（`ensure_alert_columns()` 函数），无须手动操作。

---

## 五、告警触发方式汇总

### 自动触发（7 个监控点）

| # | 文件 | 触发位置 | 异常类型 | 级别 |
|---|------|---------|---------|------|
| 1 | `plate.py:70` | 车牌识别模块导入失败 | `plate_model_load_failure` | critical |
| 2 | `plate.py:88` | 上传图片无法解码 | `plate_frame_decode_failure` | info |
| 3 | `police_gesture.py:112` | 交警手势识别异常 | `police_gesture_inference_error` | warning |
| 4 | `driver_gesture.py:48` | 车主手势模型加载失败 | `driver_gesture_model_failure` | critical |
| 5 | `driver_gesture.py:72` | 车主手势置信度 < 0.2 | `driver_gesture_low_confidence` | info |
| 6 | `auth.py:305` | 登录密码错误 | `auth_login_failure` | info |
| 7 | `auth.py:149` | 非管理员访问管理功能 | `auth_unauthorized` | warning |

### 手动测试触发

```bash
# 管理员登录获取 Token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456","portal":"admin"}'

# 用返回的 Token 调用测试接口（支持 13 种异常类型）
curl -X POST "http://localhost:8000/api/alerts/test?type=plate_recognition_failure&level=warning" \
  -H "Authorization: Bearer <token>"
```

支持的 `type` 参数值：
`plate_recognition_failure`, `plate_model_load_failure`, `plate_frame_decode_failure`, `police_gesture_low_confidence`, `police_gesture_model_failure`, `police_gesture_inference_error`, `driver_gesture_low_confidence`, `driver_gesture_model_failure`, `auth_unauthorized`, `auth_login_failure`, `llm_api_timeout`, `llm_api_error`, `system_error`

---

## 六、前端页面说明

### 6.1 告警仪表盘 (`/alerts/dashboard`)
- 4 个 KPI 统计卡片（告警总数 / 未确认 / 今日新增 / 平均响应时间）
- 告警级别分布饼图（提示 / 警告 / 严重）
- 7 日告警趋势折线图（三条曲线按级别分色）
- 异常类型分布柱状图

### 6.2 告警时间线 (`/alerts/timeline`)
- 按日期分组，每条告警显示级别标签 + 标题 + 异常类型 + 时间
- 支持按级别、异常类型筛选
- 点击卡片跳转到告警详情
- 分页浏览

### 6.3 告警详情 (`/alerts/detail/:id`)
- 基本信息（级别、标题、异常类型、来源模块、影响范围、通知渠道）
- 完整告警摘要（由 LLM 或模板生成）
- 建议处置措施（Steps 组件展示）
- 事件回放（原始事件数据 JSON 展开查看）
- 事件时间线（告警发生 → 通知发送 → 已/未确认）
- 相关告警列表（同类型前后 1 小时内）

### 6.4 告警分析 (`/alerts/analysis`)
- 4 个统计卡片（7 日总数 / 已确认 / 确认率 / 最常见异常）
- 来源模块分布饼图
- 告警峰值时段柱状图（24 小时）
- Top 10 异常类型排名柱状图
- 异常类型排名表格（含占比进度条）

### 6.5 告警中心 (`/alerts`) — 增强
- 原有功能完全保留
- 新增"异常类型"列、"详情"按钮
- 新增批量确认功能（多选 + 一键确认）
- 新增导航按钮（仪表盘 / 时间线 / 分析）
- 详情弹窗增强（影响范围 + 建议处置措施 Steps 展示）

---

## 七、权限设计

| 页面 | 管理员 | 普通用户 |
|------|--------|---------|
| 告警中心 (`/alerts`) | ✅ 全部功能 | ❌ |
| 告警仪表盘 (`/alerts/dashboard`) | ✅ | ✅ |
| 告警时间线 (`/alerts/timeline`) | ✅ | ✅ |
| 告警详情 (`/alerts/detail/:id`) | ✅ | ✅ |
| 告警分析 (`/alerts/analysis`) | ✅ | ✅ |

后端 API 对应调整：stats / timeline / detail / analysis 接口改为 `get_current_user`（任何已登录用户），test / batch-acknowledge 保留 `require_admin`。

---

## 八、依赖项

### 新增后端依赖
```
httpx>=0.27.0    # 异步 HTTP 客户端（飞书 Webhook + DeepSeek API）
```

### 无需新增前端依赖
已有的 `echarts@6.1.0` + `echarts-for-react@3.0.6` + `antd@6.5.0` 满足所有需求。

---

## 九、配置参考

完整的 AlertAgent 相关环境变量（位于 `backend/.env`）：

```bash
# ── AlertAgent 智能告警 ──
ALERT_AGENT_ENABLED=true
ALERT_DEDUP_WINDOW_SECONDS=300
ALERT_MIN_INTERVAL_SECONDS=60

# ── LLM API (DeepSeek) ──
LLM_ENABLED=true
LLM_API_KEY=sk-2382bcd8581a4decaf997bffb6acf872
LLM_API_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT=30
LLM_MAX_TOKENS=500

# ── 告警通知渠道 ──
ALERT_NOTIFICATION_ENABLED=true
ALERT_WEBSOCKET_ENABLED=true
ALERT_FEISHU_ENABLED=true
ALERT_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/f2026cea-209f-46e7-8243-44c318ddbe15
```

---

## 十、启动方式

```bash
# 1. 启动后端
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. 启动前端
cd frontend
npx vite

# 3. 访问 http://localhost:5173 使用 admin/123456 登录
# 4. 侧边栏点击"告警仪表盘"/"告警分析"等查看
```

---

## 十一、飞书通知说明

**当前状态**：飞书 Webhook 返回 `{"code":19022,"msg":"Ip Not Allowed"}`。

**原因**：飞书机器人的安全设置中开启了 IP 白名单，但未将 CarMate 后端服务器的出口 IP 加入白名单。

**解决方法**：在飞书开发者后台 → 机器人 → 安全设置 → IP 白名单，添加服务器出口 IP 或关闭 IP 白名单限制。后端代码和消息卡片格式均已就绪，飞书白名单问题解决后即可正常推送。

---

## 十二、验证结果

| 测试项 | 结果 |
|--------|------|
| 后端所有模块导入 | ✅ |
| AlertAgent 事件处理流程 | ✅ 自动生成告警 ID=6 |
| 告警级别决策引擎 | ✅ 4 项测试全部通过 |
| 防抖机制 | ✅ 同类事件 60s 内不重复 |
| 降级模板摘要生成 | ✅ 全部 13 种类型 |
| TypeScript 编译 | ✅ 零错误 |
| Vite 生产构建 | ✅ 907ms 成功 |
| 前端页面渲染 | ✅ 全部页面正常显示 |
| WebSocket 连接 + 订阅 | ✅ 前端自动订阅成功 |
| 告警 API 端点 | ✅ stats/timeline/detail/analysis/anomaly-types 全部 200 |
| 测试告警生成 | ✅ POST /api/alerts/test 成功 |
| 飞书 Webhook 连通 | ⚠️ 需后台加 IP 白名单 |

---

