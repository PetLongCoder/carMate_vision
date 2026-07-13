#  CarMate — 智能车载视觉感知系统

基于深度学习的智能车载视觉平台，集**车牌识别**、**交警手势识别**、**车主手势控车**与 **LLM 驱动的智能告警中心**于一体。

> 前端 React 19 + Ant Design 6 | 后端 FastAPI + PyTorch | MySQL | WebSocket 实时推送

---

##  核心功能

| 模块 | 说明 |
|------|------|
| 📷 **车牌识别** | 图片/视频/RTSP 流输入，YOLOv8 车辆检测 + HyperLPR3 车牌 OCR，支持 IoU 逐帧追踪 |
| 👮 **交警手势识别** | MediaPipe 姿态估计 + CTPGR + LSTM 时序分类，支持 8 类中国交警手势，视频/摄像头实时流 |
| ✋ **车主手势控车** | MediaPipe 手势追踪 + LSTM，8 种手势映射为车载控制指令（播放/音量/切歌/温度） |
| 🔔 **智能告警中心** | 系统异常自动采集 → 规则引擎决策 → LLM（DeepSeek）生成摘要 → WebSocket + 飞书实时推送 |
| 📊 **控制面板** | 识别统计、告警趋势、来源分布 ECharts 可视化，支持时间线回顾和多维分析 |
| 👤 **用户系统** | 密码/手机/邮箱/微信 Mock 四种登录方式，三级权限（公开/用户/管理员），AES-256-GCM 隐私加密 |
| 📜 **操作审计** | 全量用户操作日志，管理员可查询/过滤/导出 |

---

##  技术栈

| 层 | 技术 |
|----|------|
| **前端** | React 19 · TypeScript · Vite 8 · Ant Design 6 · Zustand · ECharts 6 · React Router 7 |
| **后端** | FastAPI · Python 3.10+ · Uvicorn · SQLAlchemy 2.0 · Pydantic v2 · Loguru |
| **AI/ML** | YOLOv8 · HyperLPR3 · MediaPipe · CTPGR (PAF + ResNet) · PyTorch LSTM |
| **数据库** | 腾讯云 MySQL (pymysql, utf8mb4) |
| **实时通信** | 原生 WebSocket (告警推送 + 车牌逐帧追踪) |
| **外部集成** | DeepSeek API (LLM 摘要) · 飞书 Webhook · QQ 邮箱 SMTP · MediaMTX 流媒体 |
| **安全** | bcrypt 密码哈希 · JWT HS256 · AES-256-GCM 隐私加密 · 三级权限守卫 |

---

##  项目结构

```
carMate_vision/
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # 应用入口, 路由注册, WebSocket, 生命周期
│   │   ├── core/                # 核心基础设施
│   │   │   ├── config.py        # 环境变量配置 (Settings 类)
│   │   │   ├── database.py      # SQLAlchemy 引擎 + 表迁移
│   │   │   ├── security.py      # bcrypt + JWT 认证
│   │   │   ├── crypto.py        # AES-256-GCM 隐私字段加解密
│   │   │   └── account_security.py  # 登录方式保护
│   │   ├── api/v1/              # REST API 路由 (11个模块, 67个端点)
│   │   │   ├── auth.py          # 用户认证 (注册/登录/绑定/解绑/注销)
│   │   │   ├── plate.py         # 车牌识别 + 视频追踪
│   │   │   ├── police_gesture.py    # 交警手势识别
│   │   │   ├── driver_gesture.py    # 车主手势控车
│   │   │   ├── alerts.py + alert_stats.py  # 告警管理 + 统计
│   │   │   ├── stats.py         # 仪表盘统计
│   │   │   ├── wechat.py        # Mock 微信登录
│   │   │   ├── history.py       # 用户识别历史
│   │   │   └── admin_logs.py + admin_history.py  # 管理后台
│   │   ├── services/            # 业务逻辑层
│   │   │   ├── plate_recognition.py     # YOLOv8 + HyperLPR3 推理
│   │   │   ├── plate_tracker.py        # IoU 逐帧车牌关联
│   │   │   ├── police_gesture_service.py  # MediaPipe + CTPGR 手势推理
│   │   │   ├── session_manager.py      # 视频会话生命周期
│   │   │   ├── video_processor.py      # 逐帧解码管道
│   │   │   ├── alert_agent/            # 智能告警 Agent 系统
│   │   │   │   ├── alert_agent.py      # 规则引擎 + 去重 + 冷却
│   │   │   │   ├── event_collector.py  # 多源事件收集
│   │   │   │   ├── llm_summary.py      # LLM 摘要 + 降级模板
│   │   │   │   ├── notification_dispatcher.py  # WS + 飞书分发
│   │   │   │   └── ws_alert_manager.py  # WebSocket 连接池
│   │   │   ├── email_service.py        # SMTP 邮件发送
│   │   │   └── operation_log_service.py  # 审计日志
│   │   ├── models/              # ORM 模型 + Pydantic Schema
│   │   └── utils/               # 日志 + 日期工具 + 密码校验
│   ├── ctpgr/                   # 交警手势识别算法库
│   ├── scripts/                 # 数据库迁移/回填脚本
│   ├── requirements.txt
│   └── .env.example
├── frontend/                    # React SPA
│   ├── src/
│   │   ├── pages/               # 16 个页面组件
│   │   │   ├── Dashboard.tsx    # 管理员控制面板
│   │   │   ├── PlateRecognition.tsx    # 车牌识别页
│   │   │   ├── PoliceGesture.tsx      # 交警手势识别页
│   │   │   ├── DriverGesture.tsx      # 车主手势控车页
│   │   │   ├── AlertCenter.tsx        # 告警中心 (管理员)
│   │   │   ├── AlertDashboard.tsx     # 告警仪表盘
│   │   │   ├── AlertTimeline.tsx      # 告警时间线
│   │   │   ├── AlertAnalysis.tsx      # 告警分析
│   │   │   └── Login.tsx / Register.tsx  # 登录注册
│   │   ├── components/          # 通用组件 (守卫/布局/表格/弹窗)
│   │   ├── store/               # Zustand 状态 (认证/UI/手势)
│   │   ├── api/                 # Axios 封装 + 拦截器
│   │   ├── hooks/               # useWebSocket (断线重连)
│   │   └── types/               # TypeScript 类型定义
│   ├── package.json
│   └── vite.config.ts
├── mediamtx/                    # MediaMTX 流媒体服务器
├── docs/                        # 设计文档
│   ├── 系统概要设计.md
│   ├── API业务逻辑文档.md
│   ├── 告警中心+控制面板-设计图.md
│   └── 启动指南.md
├── start_all.bat                # 一键启动脚本
└── .gitignore
```

---

##  快速启动

### 环境要求

- **Python** ≥ 3.10
- **Node.js** ≥ 20
- **FFmpeg**（视频预览转码需要，推荐加入 PATH）
- **NVIDIA GPU**（可选，CUDA 12.x 可加速推理）

### 一键启动 (Windows)

```bat
start_all.bat
```

自动完成：`.env` 创建 → 依赖安装 → MediaMTX → 后端 (:8000) → 前端 (:5173)

### 手动启动

```bash
# 1. 环境配置
cp backend/.env.example backend/.env    # 编辑 .env 填入你的 API Key
cp frontend/.env.example frontend/.env

# 2. 安装依赖
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# 3. 启动后端
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. 启动前端 (新终端)
cd frontend
npm run dev
```

### 访问地址

| 服务 | 地址 |
|------|------|
|  前端页面 | http://localhost:5173 |
|  后端 API | http://localhost:8000 |
|  API 文档 (Swagger) | http://localhost:8000/docs |
|  流媒体 RTSP | rtsp://localhost:8554 |

### 测试账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | `admin` | `123456` |
| 普通用户 | `user` | `123456` |

---

##  环境变量

### 后端 (`backend/.env`)

```bash
# ── 数据库 (腾讯云 MySQL) ──
DB_HOST=your-host.sql.tencentcdb.com
DB_PORT=23196
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=carmate

# ── 推理设备 ──
CARMATE_DEVICE=auto          # auto | cuda | cpu

# ── LLM 告警摘要 ──
LLM_ENABLED=true
LLM_API_KEY=your-api-key
LLM_API_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash

# ── 邮箱验证码 ──
EMAIL_PROVIDER=mock          # mock (终端输出) | smtp (真实发送)
# 若用 smtp 需填 SMTP_HOST / SMTP_USER / SMTP_PASSWORD ...

# ── 飞书告警通知 ──
ALERT_FEISHU_ENABLED=true
ALERT_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# ── 视频/手势参数 ──
CARMATE_VIDEO_SAMPLE_FPS=15
CARMATE_LABEL_TIME_OFFSET_SECONDS=0.8
```

>  完整配置项见 `backend/.env.example`

---

##  核心数据流

```
摄像头/上传 → 解码帧
  ├── 车牌管道: YOLOv8 车辆检测 → HyperLPR3 车牌OCR → IoU逐帧追踪 → PlateRecord
  ├── 交警手势: MediaPipe 姿态关键点 → CTPGR LSTM 分类 → PoliceGestureLog
  └── 车主手势: MediaPipe 手部关键点 → LSTM 分类 → 手势段跟踪 → 控制指令

系统异常 → EventCollector → AlertAgent (规则引擎 + 滑动窗口去重)
  → LLM (DeepSeek) 生成摘要 → AlertRecord (MySQL)
  → WebSocket 实时推送 + 飞书卡片通知

用户操作 → JWT 认证 → 角色鉴权 → 操作日志 (审计)
```

---

##  系统架构

详细的分层架构图和设计文档见：

- [系统概要设计](docs/系统概要设计.md) — 四层架构图 + 技术栈 + 安全设计
- [API 业务逻辑文档](docs/API业务逻辑文档.md) — 67 个端点的完整流程 + 伪代码
- [告警中心 + 控制面板设计图](docs/告警中心+控制面板-设计图.md) — 类图 + 流程图 + 时序图

---

##  License

MIT

---
