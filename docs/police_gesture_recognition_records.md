# 交警手势识别日志与识别记录说明

本文档说明交警手势识别模块如何写入日志和识别记录，以及这些记录如何在后台管理、仪表盘统计和排查工具中使用。

## 1. 功能目标

交警手势识别产生两类持久化数据：

1. 识别记录：写入 `history_records` 和 `recognition_records`，用于“识别记录管理”、用户历史记录、仪表盘主指标统计。
2. 推理日志：写入 `police_gesture_logs`，用于交警手势模块的推理明细排查，例如视频中的每个手势段、实时流段确认、失败原因等。

两者定位不同：

| 数据类型 | 表 | 主要用途 | 展示位置 |
| --- | --- | --- | --- |
| 业务识别记录 | `history_records` | 保存一次识别任务的完整摘要和结果 JSON | 管理端“识别记录管理”、用户历史 |
| 统计识别记录 | `recognition_records` | 轻量统计表，保存类型、摘要、置信度、成功状态 | 仪表盘手势主指标 |
| 交警推理日志 | `police_gesture_logs` | 保存交警手势推理明细和分段日志 | 交警手势日志查询、仪表盘日志页 |

## 2. 相关文件

| 文件 | 作用 |
| --- | --- |
| `backend/app/api/v1/police_gesture.py` | 交警手势 API 入口，负责调用识别服务并写入业务识别记录 |
| `backend/app/services/police_gesture_service.py` | 模型推理、视频分段、流式识别、流式记录写入 |
| `backend/app/services/record_service.py` | 统一识别记录服务，写入 `history_records` 和 `recognition_records` |
| `backend/app/services/police_gesture_logger.py` | 交警手势推理日志服务，异步写入 `police_gesture_logs` |
| `backend/app/models/db_models.py` | 三张表的 ORM 定义 |
| `backend/app/api/v1/admin_history.py` | 管理端识别记录查询接口 |
| `backend/app/api/v1/stats.py` | 仪表盘统计接口 |
| `frontend/src/pages/AdminRecognitionRecords.tsx` | 管理端识别记录管理页面 |
| `frontend/src/pages/DashboardGestureStats.tsx` | 手势统计和日志入口页面 |

## 3. 数据写入流程

### 3.1 图片/普通视频上传

接口：

```text
POST /api/police-gesture/recognize
```

流程：

1. 前端上传图片或视频。
2. 后端根据文件扩展名判断 `source_type`：
   - 图片：`image`
   - 视频：`video`
3. 后端调用：
   - 图片：`process_police_gesture_image`
   - 视频：`process_police_gesture_video`
4. API 层调用 `log_recognition` 写入：
   - `history_records`
   - `recognition_records`
5. 视频识别服务额外按手势段写入 `police_gesture_logs`。

普通视频结果中包含 `segments`。`build_gesture_summary` 会优先从 `segments` 中提取全部有效手势，按出现顺序去重后生成摘要，例如：

```text
停止、直行、左转
```

如果没有 `segments`，则回退为单个综合动作：

```text
停止 (92%)
```

### 3.2 流式视频识别

接口：

```text
POST /api/police-gesture/recognize/stream
```

流程：

1. 后端通过 SSE 持续返回分析进度和逐帧结果。
2. 分析完成后生成最终 `result`，包含：
   - `gesture`
   - `confidence`
   - `top5`
   - `frames`
   - `segments`
3. 服务层调用 `_write_stream_recognition_record` 写入：
   - `history_records`
   - `recognition_records`
4. 摘要使用 `build_gesture_summary(result)`，因此也会显示全部识别出的手势。
5. 每个视频手势段会作为推理日志写入 `police_gesture_logs`，同一视频共享同一个 `video_session_id`。

### 3.3 摄像头实时帧识别

接口：

```text
POST /api/police-gesture/stream/frame
```

流程：

1. 前端周期性上传摄像头截图。
2. 后端维护每个 `stream_id` 的 LSTM 状态、历史帧、稳定结果和手势段。
3. 当 `segmentChanged` 为 `true` 时，说明出现了新的稳定手势段。
4. API 层调用 `log_recognition` 写入识别记录，`source_type` 为 `camera_stream`。
5. 服务层同步写入交警推理日志，记录当前段的手势、置信度、Top-5 和段信息。

实时流不会每一帧都写业务识别记录，只有确认新段时才写，避免后台记录页被大量重复帧淹没。

## 4. 数据表说明

### 4.1 `history_records`

用于保存可查看的历史识别记录。

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 用户 ID，未登录时为空 |
| `type` | 识别类型，交警手势为 `police_gesture` |
| `session_id` | 会话 ID，流式/实时场景用于关联 |
| `image_url` | 图片地址，当前交警手势记录通常为空 |
| `result_json` | 识别结果 JSON，包含摘要、文件名、来源、成功状态等 |
| `created_at` | 创建时间 |

交警手势写入 `result_json` 时会剥离体积较大的逐帧数据：

```python
payload.pop("frames", None)
payload.pop("segments", None)
```

摘要会单独保存到 `payload["summary"]`，因此后台列表不依赖完整逐帧数据也能显示多手势摘要。

### 4.2 `recognition_records`

用于统计和快速查询。

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 用户 ID |
| `type` | `police_gesture` / `driver_gesture` / `plate` |
| `result_summary` | 识别摘要，最长 255 字符 |
| `confidence` | 置信度 |
| `success` | 是否成功 |
| `created_at` | 创建时间 |

仪表盘中的手势总数、今日手势数、成功手势数来自这张表。

### 4.3 `police_gesture_logs`

用于交警手势推理明细。

| 字段 | 说明 |
| --- | --- |
| `recognition_type` | `image` / `video` / `video_stream` / `camera_stream` |
| `video_session_id` | 同一视频的多个手势段共享同一个 UUID |
| `filename` | 上传文件名 |
| `gesture` | 手势名称 |
| `gesture_id` | 手势 ID，`0` 表示无手势 |
| `confidence` | 置信度 |
| `inference_ms` | 推理耗时 |
| `top5_json` | Top-5 候选 JSON |
| `frames_total` | 视频总帧数 |
| `frames_processed` | 实际处理帧数 |
| `video_fps` | 视频帧率 |
| `video_duration` | 视频时长 |
| `segments_json` | 当前日志对应的手势段 JSON |
| `success` | 是否成功 |
| `error_message` | 失败原因 |
| `client_info` | 客户端 IP / User-Agent 摘要 |
| `created_at` | 创建时间 |

## 5. 摘要生成规则

统一入口：

```python
build_gesture_summary(data)
```

规则：

1. 如果 `data.segments` 存在，提取 `gestureId > 0` 的手势名称。
2. 按出现顺序去重。
3. 使用 `、` 拼接为摘要。
4. 如果没有有效段，回退到 `gesture` 或 `gesture_name`。
5. 如果有 `confidence`，单动作摘要显示为 `动作名 (百分比)`。
6. 如果仍没有识别结果，显示 `未识别`。

示例：

```json
{
  "gesture": "停止",
  "confidence": 0.91,
  "segments": [
    {"start": 0.5, "end": 2.0, "gesture": "停止", "gestureId": 1},
    {"start": 3.0, "end": 5.0, "gesture": "直行", "gestureId": 2},
    {"start": 7.0, "end": 8.0, "gesture": "停止", "gestureId": 1}
  ]
}
```

后台摘要：

```text
停止、直行
```

## 6. 查询接口

### 6.1 管理端识别记录

```text
GET /api/admin/recognition-records
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `page` | 页码 |
| `pageSize` | 每页数量 |
| `type` | 识别类型，交警手势为 `police_gesture` |
| `sourceType` | 来源类型，如 `image`、`video`、`video_stream`、`camera_stream` |
| `success` | 是否成功 |
| `keyword` | 关键字 |
| `username` | 用户名 |
| `startDate` | 开始时间 |
| `endDate` | 结束时间 |

返回数据由 `history_record_to_dict` 统一转换，其中 `summary` 字段用于列表摘要列。

### 6.2 当前用户历史记录

```text
GET /api/history
```

用于当前登录用户查看自己的识别历史。数据来源同样是 `history_records`。

### 6.3 交警手势推理日志

```text
GET /api/police-gesture/logs
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `page` | 页码 |
| `page_size` | 每页数量 |
| `recognition_type` | `image` / `video` / `video_stream` / `camera_stream` |
| `gesture` | 手势名称 |

该接口查询的是 `police_gesture_logs`，用于排查模型推理细节，不等同于识别记录管理列表。

## 7. 日志级别与环境变量

### 7.1 应用日志级别

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CARMATE_LOG_LEVEL` | `INFO` | 全局日志级别 |
| `CARMATE_LOG_LEVEL_POLICE_GESTURE` | 跟随全局 | 交警手势模块日志级别 |

示例：

```powershell
$env:CARMATE_LOG_LEVEL_POLICE_GESTURE = "DEBUG"
```

### 7.2 数据库推理日志写入级别

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CARMATE_GESTURE_LOG_LEVEL` | `segment` | 控制 `police_gesture_logs` 写入详细程度 |

可选值：

| 值 | 行为 |
| --- | --- |
| `segment` | 默认模式，仅写识别完成、视频手势段、实时流段确认等关键日志 |
| `full` | 写入更多帧级日志，主要用于调试 |
| `error` | 仅写失败日志 |

生产环境建议使用 `segment`，避免实时流场景产生过多日志。

## 8. 前端展示口径

### 8.1 识别记录管理

页面：

```text
frontend/src/pages/AdminRecognitionRecords.tsx
```

列表中的摘要列读取 `record.summary`。如果后端没有返回摘要，前端会依次回退到：

1. 车牌号
2. 车牌数组
3. `result.gesture`
4. `-`

因此交警手势多动作摘要应尽量在后端生成并保存。

### 8.2 仪表盘统计

接口：

```text
GET /api/stats/dashboard
```

手势主指标来自 `recognition_records`：

| 指标 | 来源 |
| --- | --- |
| `gestureRecordTotal` | 所有 `police_gesture` + `driver_gesture` 记录 |
| `gestureRecordToday` | 今日手势记录 |
| `gestureRecordSuccess` | 成功手势记录 |

交警推理日志单独作为 `policeInferenceLogs` 展示，不参与主指标求和，避免“一个视频多个手势段”导致业务识别次数膨胀。

## 9. 排查建议

### 9.1 后台只显示一个动作

检查顺序：

1. 视频结果中是否生成了 `segments`。
2. `build_gesture_summary(result)` 是否返回多个手势。
3. `history_records.result_json` 中是否保存了 `summary`。
4. 管理端接口 `/api/admin/recognition-records` 返回的 `summary` 是否正确。

注意：旧记录如果当时只保存了单动作摘要，且 `segments` 已被剥离，无法自动恢复多动作摘要，需要重新识别视频。

### 9.2 识别记录管理没有实时流记录

检查：

1. 实时帧返回数据中 `segmentChanged` 是否为 `true`。
2. `gestureId` 是否大于 0。
3. `POST /api/police-gesture/stream/frame` 是否成功调用 `log_recognition`。
4. 数据库中 `history_records.type = 'police_gesture'` 且 `sourceType = 'camera_stream'` 的记录是否存在。

### 9.3 推理日志数量过多

检查 `CARMATE_GESTURE_LOG_LEVEL`：

```text
segment: 推荐，日志量适中
full: 调试用，可能产生大量日志
error: 只保留失败日志
```

### 9.4 仪表盘数量和日志数量不一致

这是预期行为：

- 仪表盘主指标看 `recognition_records`，代表业务识别次数。
- 推理日志看 `police_gesture_logs`，一个视频可能对应多个手势段日志。

## 10. 验证清单

功能改动后建议验证：

1. 上传包含多个手势的视频。
2. 进入“识别记录管理”。
3. 筛选类型为“交警手势”。
4. 确认视频记录摘要展示多个手势，例如 `停止、直行、左转`。
5. 打开详情，确认 `result.summary` 与列表一致。
6. 打开仪表盘手势统计，确认主指标数量正常。
7. 查询交警手势日志，确认视频手势段按 `videoSessionId` 分组。
8. 摄像头实时识别时，做出稳定手势段后确认识别记录中新增 `camera_stream` 来源记录。

