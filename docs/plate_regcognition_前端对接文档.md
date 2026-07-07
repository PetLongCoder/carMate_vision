# 车牌识别模块 — 前后端交互实现

> 本文档从代码层面说明车牌识别功能在前端和后端之间的交互流程、数据格式、关键实现细节。

---

## 目录

1. [模块整体架构](#1-模块整体架构)
2. [后端实现 — 核心服务层](#2-后端实现--核心服务层)
3. [后端实现 — API 层](#3-后端实现--api-层)
4. [前端实现 — API 调用层](#4-前端实现--api-调用层)
5. [前端实现 — 页面展示层](#5-前端实现--页面展示层)
6. [交互流程图](#6-交互流程图)
7. [关键实现细节](#7-关键实现细节)

---

## 1. 模块整体架构

```
┌──────────────────────────────┐
│     前端 React 页面           │
│  PlateRecognition.tsx        │
│  ┌──────────────────────┐    │
│  │ 图片/视频 Tab → upload │    │
│  │ 实时追踪 Tab → track   │    │
│  │ 流媒体   Tab → stream  │    │
│  └──────┬───────────────┘    │
│         │ REST / WebSocket   │
│    ┌────┴────┐               │
│    │  api/   │               │
│    │ index.ts│               │
│    └────┬────┘               │
└─────────┼────────────────────┘
          │ HTTP / WS
┌─────────┼────────────────────┐
│  Vite Proxy (开发环境)       │
└─────────┼────────────────────┘
          │
┌─────────┴────────────────────┐
│     后端 FastAPI             │
│  ┌──────────────────────┐    │
│  │ router: plate.py      │    │
│  │ POST /plate/recognize │    │
│  │ POST /plate/track     │    │
│  │ POST /plate/stream/*  │    │
│  │ WS  /plate/track/{id} │    │
│  └────┬─────────────────┘    │
│  ┌────┴─────────────────┐    │
│  │ service:              │    │
│  │ plate_recognition.py  │    │
│  │ session_manager.py    │    │
│  │ video_processor.py    │    │
│  └──────────────────────┘    │
└──────────────────────────────┘
```

---

## 2. 后端实现 — 核心服务层

### 2.1 车牌识别引擎 (`plate_recognition.py`)

#### 关键类

```python
class PlateRecognizer:
    """HyperLPR3 车牌识别器"""

    def __init__(self, detect_level: int = None):
        # 初始化时预创建两个 catcher 实例
        # LOW: 速度优先, HIGH: 精度优先
        self._catcher_low = lpr3.LicensePlateCatcher(detect_level=DETECT_LEVEL_LOW)
        self._catcher_high = lpr3.LicensePlateCatcher(detect_level=DETECT_LEVEL_HIGH)
        self.catcher = self._catcher_low  # 默认 LOW

    def detect_on_full_image(self, image: np.ndarray) -> list[dict]:
        """
        核心检测方法: 全图检测并识别车牌
        返回: [{"plate_no", "color", "confidence", "bbox"}, ...]

        实现要点:
        1. 仅在原图上跑一次 HyperLPR3 检测
        2. 去重: 同一车牌号只保留置信度最高的
        3. 过滤: confidence < 0.5 直接丢弃, 避免误检
        """

    def set_detect_level(self, level: int):
        """切换检测精度级别, 切换成本≈0ms (指针赋值)"""
        self.catcher = self._catcher_high if level else self._catcher_low
```

#### 单例管理

```python
# 模块级单例, 避免重复加载模型
_recognizer: Optional[PlateRecognizer] = None

def get_recognizer() -> PlateRecognizer:
    global _recognizer
    if _recognizer is None:
        _recognizer = PlateRecognizer()
    return _recognizer
```

#### 图片识别 pipeline

```python
def recognize_plates(image: np.ndarray) -> list[dict]:
    """
    完整 pipeline:

    1. HyperLPR3 全图检测+识别车牌
    2. YOLOv8 车辆检测 (辅助, 获取车辆类型)
    3. 车牌→车辆匹配 (中心点是否在车辆框内)
    4. 组装结果, 含车辆类型信息

    返回: PlateResult[] 格式
    """
    recognizer = get_recognizer()
    detector = get_detector()

    plates = recognizer.detect_on_full_image(image)
    if not plates:
        return []

    vehicles = detector.detect(image)

    results = []
    for i, plate in enumerate(plates):
        matched_vehicle = _match_plate_to_vehicle(plate["bbox"], vehicles)
        vehicle_type = matched_vehicle["class_name"] if matched_vehicle else "unknown"

        results.append({
            "carId": i + 1,
            "plateNo": plate["plate_no"],
            "vehicleType": vehicle_type,
            "color": plate["color"],
            "confidence": plate["confidence"],
            "bbox": plate["bbox"],
        })
    return results
```

#### 视频识别 pipeline

```python
def recognize_plates_from_video(video_bytes: bytes) -> list[dict]:
    """
    全帧率处理 + 去重合并

    实现:
    1. 写入临时文件
    2. VideoCapture 逐帧读取, 但仅采样 ~1帧/秒
    3. 每帧调用 recognize_plates()
    4. 模糊去重: 用 _plates_are_same() 合并相似车牌

    _plates_are_same 算法:
    - 提取字母数字核心 ("鄂W3U060" → "W3U060")
    - 后 5 位匹配则同一车牌
    - 编辑距离相似度 >= 0.55 则同一车牌
    """
```

### 2.2 会话管理层 (`session_manager.py`)

管理视频追踪和流媒体追踪的会话生命周期：

```python
class TrackingSession:
    """
    一个追踪会话代表一次视频/流媒体追踪任务

    属性:
    - session_id: 唯一标识 (如 "vid_abc123")
    - type: VIDEO 或 STREAM
    - status: pending → processing → completed/error/stopped
    - total_frames / processed_frames: 进度追踪
    - ws_connections: 当前 WebSocket 连接数

    关键方法:
    - update_status(): 更新状态
    - to_dict(): 转为 API 响应格式
    - add_ws_connection() / remove_ws_connection(): WS 连接管理
    """

class SessionManager:
    """全局会话管理器, 维护所有活跃会话"""

    def __init__(self):
        self._sessions: dict[str, TrackingSession] = {}

    async def create_session(self, type, source, total_frames) -> TrackingSession
    async def get_session(self, session_id) -> TrackingSession | None
    async def list_sessions(self) -> list[dict]
    async def broadcast(self, session_id, message):  # 向所有 WS 客户端广播
```

### 2.3 视频处理器 (`video_processor.py`)

```python
async def run_video_session(session: TrackingSession):
    """
    视频/流媒体追踪任务入口。

    实现:
    1. 从 session.source 获取帧 (视频文件路径 / 流地址)
    2. 对每帧执行车辆检测 + 车牌 OCR (裁剪区域)
    3. 每帧结果通过 WebSocket 广播
    4. 处理完成后发送 summary
    """
```

---

## 3. 后端实现 — API 层

### 3.1 路由文件 `plate.py`

有两个主要版本共存：

#### 版本 A: 简单上传识别

```python
POST /api/plate/recognize

# 功能: 上传图片/视频, 同步返回识别结果
# 图片: 直接识别 → 返回 PlateResult[]
# 视频: 写入临时文件 → 采样识别 → 去重合并 → 返回 PlateResult[]

# 实现逻辑:
@router.post("/plate/recognize")
async def recognize_plate(file: UploadFile = File(...)):
    contents = await file.read()
    is_video = 根据扩展名或 MIME 判断

    if is_video:
        plates = recognize_plates_from_video(contents)
    else:
        image = cv2.imdecode(...)
        plates = recognize_plates(image)

    return {"code": 200, "message": "识别完成", "data": plates}
```

#### 版本 B: 视频追踪 (WebSocket)

```python
POST /api/plate/track
# 功能: 上传视频, 创建追踪会话, 返回 sessionId
# 前端通过 WebSocket 连接后, 后端逐帧推结果

POST /api/plate/stream/start
# 功能: 接入 RTSP/RTMP 流, 启动实时追踪

POST /api/plate/stream/stop/{session_id}
# 功能: 停止指定会话

GET /api/plate/stream/sessions
GET /api/plate/stream/sessions/{session_id}
# 功能: 查询会话状态

# WebSocket 端点 (在单独文件中)
ws://host/api/ws/plate/track/{session_id}
# 功能: 接收逐帧检测结果
```

---

## 4. 前端实现 — API 调用层

### 4.1 文件结构

```
frontend/src/
├── api/
│   ├── request.ts      # Axios 实例 (baseURL, 拦截器)
│   └── index.ts        # 所有 API 函数
├── types/
│   └── index.ts        # TypeScript 类型定义
└── pages/
    └── PlateRecognition.tsx   # 页面组件
```

### 4.2 Axios 配置 (`request.ts`)

```typescript
const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// 请求拦截器: 自动携带 token
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// 响应拦截器: 统一错误处理
request.interceptors.response.use(
  (response) => {
    const res = response.data;
    if (res.code !== 200) return Promise.reject(new Error(res.message));
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  },
);
```

### 4.3 API 函数 (`index.ts`)

```typescript
// 图片/视频上传识别
export function uploadPlateImage(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<PlateResult[]>>('/plate/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

// 视频追踪
export function uploadTrackVideo(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request.post<ApiResponse<TrackSessionResponse>>('/plate/track', formData, {
    timeout: 30000,
  });
}

// 流媒体
export function startStreamTracking(url: string, name?: string) { ... }
export function stopStreamTracking(sessionId: string) { ... }
```

### 4.4 Vite Proxy 配置 (`vite.config.ts`)

开发环境通过 Vite proxy 转发 API 请求和 WebSocket 连接，避免跨域：

```typescript
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
    '/ws': {
      target: 'ws://localhost:8000',
      ws: true,
    },
  },
},
```

---

## 5. 前端实现 — 页面展示层

### 5.1 组件状态设计

```typescript
// 页面有三种模式
type PageMode = 'upload' | 'track' | 'stream';

const PlateRecognition: React.FC = () => {
  // ── Upload 模式状态 ──
  const [results, setResults] = useState<PlateResult[]>([]);  // 识别结果
  const [previewUrl, setPreviewUrl] = useState<string | null>(null); // 预览图/视频
  const [isVideo, setIsVideo] = useState(false);             // 是否为视频
  const [imageScale, setImageScale] = useState({ x: 1, y: 1 }); // 缩放比

  // ── Track 模式状态 ──
  const [trackSessionId, setTrackSessionId] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [currentDetections, setCurrentDetections] = useState<TrackedPlateResult[]>([]);
  const [trackedPlates, setTrackedPlates] = useState<TrackedPlateSummary[]>([]);

  // ── Stream 模式状态 ──
  const [streamUrl, setStreamUrl] = useState('');
  // ...
};
```

### 5.2 Upload 模式 — 交互流程

```
用户拖拽文件到 Dragger
    ↓
handleUpload(file)
    ├── 判断是否为视频
    ├── FileReader 读取 → 显示预览
    └── uploadPlateImage(file) → API
        ↓
    后端返回 PlateResult[]
    ↓
    若为图片: bbox 叠加预览 (CSS 绝对定位 + scale 缩放)
    若为视频: <video> 播放 + 底部表格展示结果
```

**图片 bbox 叠加实现**：

```typescript
// 计算显示比例
const handleImageLoad = (e) => {
  const img = e.currentTarget;
  setScale({
    x: img.clientWidth / img.naturalWidth,
    y: img.clientHeight / img.naturalHeight,
  });
};

// CSS 渲染
{results.map((r) => (
  <div key={r.carId} style={{
    position: 'absolute',
    left: r.bbox.x * scale.x,
    top: r.bbox.y * scale.y,
    width: r.bbox.width * scale.x,
    height: r.bbox.height * scale.y,
    border: '2px solid #1677ff',
    pointerEvents: 'none',  // 不阻挡点击
  }}>
    <span>{r.plateNo}</span>
  </div>
))}
```

### 5.3 Track 模式 — 交互流程

```
用户拖拽视频到 Dragger
    ↓
handleTrackUpload(file)
    ├── FileReader → 本地视频预览
    └── uploadTrackVideo(file) → 后端
        ↓
    后端返回 { sessionId, totalFrames, wsEndpoint }
    ↓
    connectWs(sessionId)
    ↓
    WebSocket 建立连接
    ↓
    onmessage: 'detection' → 更新 currentDetections
    onmessage: 'status'    → 更新进度条
    onmessage: 'summary'   → 更新汇总表格, 追踪结束
```

**Canvas 叠加实现**：

```typescript
// requestAnimationFrame 循环
const drawLoop = () => {
  const currentTime = video.currentTime;

  // 从 allDetections Map 中找到当前时间最近的检测结果
  allDetections.forEach((dets, frameNum) => {
    const estTime = frameNum / totalFrames * duration;
    if (abs(estTime - currentTime) < bestDiff) {
      bestDetections = dets;
    }
  });

  drawDetectionsOnCanvas(canvas, video, bestDetections);
  requestAnimationFrame(drawLoop);
};
```

Canvas 绘制 (`drawDetectionsOnCanvas`):

```typescript
function drawDetectionsOnCanvas(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
  detections: TrackedPlateResult[],
) {
  const ctx = canvas.getContext('2d');
  const rect = video.getBoundingClientRect();  // 实际显示尺寸
  const scaleX = rect.width / video.videoWidth;   // 缩放比
  const scaleY = rect.height / video.videoHeight;

  ctx.clearRect(0, 0, rect.width, rect.height);

  for (const d of detections) {
    const x = d.bbox.x * scaleX;
    const y = d.bbox.y * scaleY;
    const color = getColorForPlate(d.color);

    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);

    // 标签背景
    ctx.fillStyle = color;
    ctx.roundRect(labelX, labelY - 24, tw + 16, 24, 4);
    ctx.fill();

    // 标签文字
    ctx.fillStyle = '#fff';
    ctx.fillText(d.plateNo, labelX + 8, labelY - 7);
  }
}
```

Canvas 通过 CSS 叠加在 video 上：

```tsx
<div style={{ position: 'relative' }}>
  <video ref={videoRef} src={previewUrl} controls
    style={{ maxWidth: '100%', maxHeight: 450 }} />
  <canvas ref={canvasRef}
    style={{
      position: 'absolute', top: 0, left: 0,
      width: '100%', height: '100%',
      pointerEvents: 'none',           // 点击穿透到 video
    }}
  />
</div>
```

---

## 6. 交互流程图

### 6.1 图片识别

```
前端                          后端                    HyperLPR3 + YOLO
 │                             │                         │
 │ POST /plate/recognize       │                         │
 │ file: image.jpg ──────────► │                         │
 │                             │ cv2.imdecode()          │
 │                             │ recognize_plates() ────►│
 │                             │   ├── detect_on_full()  │
 │                             │   │   → 车牌检测+识别    │
 │                             │   └── VehicleDetector() │
 │                             │       → 车辆类型识别     │
 │                             │◄────────────────────────│
 │ ◄──── PlateResult[] ────── │                         │
 │                             │                         │
 │ 计算 scale (自然/显示尺寸)   │                         │
 │ CSS 定位渲染 bbox + 标签     │                         │
 │ 展示结果表格                 │                         │
```

### 6.2 视频识别

```
前端                          后端
 │                             │
 │ POST /plate/recognize       │
 │ file: video.mp4 ──────────► │
 │                             │ 写入临时文件
 │                             │ VideoCapture 逐帧读取
 │                             │ 采样 ~1帧/秒
 │                             │ 每帧 → recognize_plates()
 │                             │ 模糊去重合并
 │ ◄─── PlateResult[] ─────── │
 │                             │
 │ <video> 播放预览            │
 │ 表格展示结果 (含 timestamp)  │
```

### 6.3 实时追踪 (WebSocket)

```
前端                          后端
 │                             │
 │ POST /plate/track ────────► │
 │ ◄─── { sessionId } ─────── │
 │                             │
 │ WS connect ───────────────► │
 │                             │
 │ (处理中...)                  │
 │ ◄─── status: processing ─── │
 │ ◄─── detection frame=0 ──── │  ← 每帧都推
 │    (更新 canvas + 日志)      │
 │ ◄─── detection frame=1 ──── │
 │    (更新 canvas + 日志)      │
 │ ◄─── detection frame=N ──── │
 │                             │
 │ ◄─── status: completed ──── │
 │ ◄─── summary ───────────── │
 │                             │
 │ requestAnimationFrame       │
 │ 从 currentTime 查找最近帧    │
 │ Canvas 绘制实时检测框        │
 │ 展示汇总表格                 │
```

---

## 7. 关键实现细节

### 7.1 图片预览缩放 (bbox 坐标映射)

图片在屏幕上的显示尺寸和图片原始尺寸不同，bbox 需要按比例换算：

```
scaleX = img.clientWidth  / img.naturalWidth
scaleY = img.clientHeight / img.naturalHeight

渲染位置 = bbox * scale
```

使用 `jsx` 中 `<img>` 的 `onLoad` 事件获取自然尺寸，`clientWidth` 获取显示尺寸。

### 7.2 视频 + Canvas 叠加

视频模式下不支持 CSS 定位 bbox（视频的播放进度会移动），改用 Canvas 绘制：

```
1. <video> + <canvas> 同容器, canvas z-index 在上
2. canvas pointerEvents: 'none' (不阻塞 video 的点击控制)
3. drawDetectionsOnCanvas() 根据 video.currentTime 找对应检测结果
4. requestAnimationFrame 循环持续重绘
```

### 7.3 WebSocket 长连接管理

```typescript
// 连接前关闭旧连接
if (wsRef.current) wsRef.current.close();

// 组件卸载时清理
useEffect(() => {
  return () => {
    if (wsRef.current) wsRef.current.close();
    cancelAnimationFrame(animFrameRef.current);
  };
}, []);
```

### 7.4 置信度阈值

后端在 `detect_on_full_image()` 中统一过滤：

```python
conf < 0.5 → continue  # 不返回给前端
```

### 7.5 模糊去重 (视频模式)

视频模式下同一辆车可能在多帧出现，需要去重：

```python
def _plate_core(s: str) -> str:
    """提取字母数字核心: '鄂W3U060' → 'W3U060'"""

def _plates_are_same(a: str, b: str, threshold=0.55) -> bool:
    """
    1. 完全相等 → True
    2. 后5位核心字母数字相同 → True (处理 OCR 多字/少字)
    3. 编辑距离相似度 >= 0.55 → True
    4. 否则 → False
    """
```

### 7.6 文件类型自动识别

后端根据文件扩展名和 MIME type 判断是图片还是视频：

```python
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}

is_video = ext in VIDEO_EXTENSIONS or file.content_type.startswith("video/")
```

前端的判断与后端一致：

```typescript
function isVideoFile(file: File): boolean {
  const ext = '.' + file.name.split('.').pop()?.toLowerCase();
  if (VIDEO_EXTENSIONS.includes(ext)) return true;
  return file.type.startsWith('video/');
}
```

---

> **相关文件索引**
>
> | 文件 | 说明 |
> |------|------|
> | `backend/app/api/v1/plate.py` | 后端 API 路由 |
> | `backend/app/services/plate_recognition.py` | 核心车牌识别服务 |
> | `backend/app/services/session_manager.py` | 追踪会话管理 |
> | `backend/app/services/video_processor.py` | 视频/流处理引擎 |
> | `frontend/src/api/index.ts` | 前端 API 调用 |
> | `frontend/src/types/index.ts` | TypeScript 类型定义 |
> | `frontend/src/pages/PlateRecognition.tsx` | 前端页面组件 |
> | `frontend/vite.config.ts` | Vite 代理配置 |
