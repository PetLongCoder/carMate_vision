# 交警手势识别模块开发文档

## 1. 模块目标

本模块用于识别交通警察指挥手势。用户在前端上传图片或视频后，后端调用预训练的 `ctpgr-pytorch` 模型进行推理，并返回识别结果、置信度、逐帧结果和视频手势时间段。

本阶段重点是验证交警手势识别模型能否在当前项目中正常加载、推理和返回结果。

## 2. 功能范围

- 支持上传图片进行单帧交警手势识别。
- 支持上传视频进行序列化交警手势识别。
- 支持 9 类输出：
  - 0：无手势
  - 1：停止
  - 2：直行
  - 3：左转
  - 4：左转待转
  - 5：右转
  - 6：变道
  - 7：减速慢行
  - 8：靠边停车
- 视频识别结果包含：
  - 综合识别手势
  - 置信度
  - Top-5 手势分布
  - 视频时长和帧率
  - 已分析帧数
  - 每个采样帧的识别结果
  - 连续手势时间段

## 3. 技术方案

### 3.1 模型架构

当前后端使用 `ctpgr-pytorch` 项目中的预训练模型，整体流程为：

```text
视频/图片输入
    ↓
OpenCV 读取图像帧
    ↓
人体关键点姿态估计模型 Pose Estimation
    ↓
骨骼长度和角度特征提取 BoneLengthAngle
    ↓
LSTM 手势分类模型
    ↓
输出 0-8 类交警手势
```

相关模型文件：

- `backend/ctpgr/checkpoints/pose_model.pt`
- `backend/ctpgr/checkpoints/lstm.pt`

核心后端入口：

- `backend/server.py`

### 3.2 图片推理

图片推理使用单帧识别逻辑：

1. 前端上传图片。
2. 后端读取图片并转换为 OpenCV BGR 格式。
3. 姿态估计模型提取人体关键点。
4. LSTM 分类模型输出手势类别。
5. 后端返回手势名称、类别 ID、置信度和 Top-5 结果。

### 3.3 视频推理

视频推理使用序列识别逻辑：

1. 后端通过 OpenCV 读取视频。
2. 按采样间隔抽取视频帧，目前约为 `2fps`。
3. 每个采样帧使用等比例缩放和居中补边处理到 `512x512`。
4. 同一个视频内保留 LSTM 的隐藏状态 `h/c`，避免把序列模型退化成单帧模型。
5. 对所有采样帧进行投票，得到视频级识别结果。
6. 合并连续的非 0 手势，生成手势时间段。

## 4. 后端接口

### 4.1 健康检查

```http
GET /api/health
```

示例返回：

```json
{
  "status": "ok",
  "model": "ctpgr-pytorch (Pose + LSTM)",
  "classes": 9,
  "device": "cpu",
  "device_mode": "cpu"
}
```

### 4.2 交警手势识别

```http
POST /api/police-gesture/recognize
Content-Type: multipart/form-data
```

请求参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| file | File | 图片或视频文件 |

支持格式：

- 图片：常见图片格式
- 视频：`.mp4`、`.avi`、`.mov`、`.webm`、`.mkv`

视频返回字段说明：

| 字段 | 说明 |
| --- | --- |
| gesture | 综合识别手势名称 |
| gestureId | 综合识别类别 ID |
| confidence | 综合置信度 |
| top5 | 手势分布 |
| inference_ms | 推理耗时 |
| video_duration | 视频时长 |
| video_fps | 视频帧率 |
| frames_processed | 已分析帧数 |
| frames | 每个采样帧的识别结果 |
| segments | 连续手势时间段 |

## 5. 今日完成内容

### 5.1 接入并验证 ctpgr-pytorch 模型

后端已接入姿态估计模型和 LSTM 手势分类模型，并在服务启动时预加载模型，避免第一次请求时加载时间过长。

### 5.2 修复视频全部显示为 0 手势的问题

最初测试视频识别结果显示为 0 手势，主要原因有两个：

1. 原视频处理逻辑最多只抽取 30 帧。对于长视频来说，采样过稀，可能跳过有效动作。
2. LSTM 是序列模型，但原逻辑每帧都重置隐藏状态，导致模型无法利用动作序列信息。

已完成修复：

- 视频采样改为约 `2fps`。
- 同一个视频内保留 LSTM 隐藏状态。
- 视频帧处理改为等比例缩放和居中补边，避免直接拉伸人体。

### 5.3 处理 Windows 下 CUDA 原生崩溃问题

测试时出现过 `python.exe - 应用程序错误`，属于底层库原生崩溃，通常由 CUDA/PyTorch/OpenCV 等组件触发，不会显示普通 Python traceback。

当前处理方案：

- 后端默认使用 CPU 推理，优先保证模型链路稳定。
- 如需尝试 GPU，可设置环境变量：

```powershell
$env:CARMATE_DEVICE="cuda"
python server.py
```

如果 GPU 模式仍然弹出 `python.exe` 应用程序错误，建议继续使用 CPU 模式，后续再单独排查 CUDA、显卡驱动和 PyTorch 版本兼容性。

### 5.4 修复 CUDA 权重在 CPU 模式下无法加载的问题

由于模型权重可能是在 CUDA 设备上保存的，CPU 模式直接加载会报错：

```text
Attempting to deserialize object on a CUDA device but torch.cuda.is_available() is False
```

已在模型加载处增加：

```python
torch.load(..., map_location=self.device)
```

保证 CPU/GPU 模式都可以加载权重。

### 5.5 优化前端上传体验

视频推理耗时较长，原前端上传接口超时时间为 60 秒，长视频容易在后端还在推理时被前端中断。

已完成优化：

- 交警手势上传接口超时时间调整为 10 分钟。
- 错误提示区分为：
  - 无法连接后端服务
  - 识别超时
  - 后端返回的具体错误信息

## 6. 启动和测试步骤

### 6.1 启动后端

```powershell
cd D:\code\carMate_vision\carMate_vision\backend
python server.py
```

启动成功标志：

```text
模型预加载完成
CarMate 推理服务已启动 (ctpgr-pytorch)
Uvicorn running on http://0.0.0.0:8000
```

如果出现端口占用：

```text
[Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000)
```

说明已有后端进程占用 `8000` 端口。可以先检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

如果返回 `status: ok`，说明后端已经在运行，不需要重复启动。

### 6.2 启动前端

```powershell
cd D:\code\carMate_vision\carMate_vision\frontend
npm.cmd run dev
```

然后打开 Vite 输出的地址，通常是：

```text
http://localhost:5173
```

### 6.3 页面测试

1. 打开前端页面。
2. 进入“交警手势识别”模块。
3. 上传测试视频或图片。
4. 查看识别结果、手势分布、逐帧识别结果和手势时间线。

建议首次测试使用 20-60 秒短视频。完整长视频在 CPU 模式下推理会比较慢。

## 7. 常见问题

### 7.1 为什么显示 0 个手势段？

`gestureId=0` 表示“无手势”。前端只会把 `gestureId > 0` 的连续结果合并为手势段。如果模型大部分帧都判断为 0，就会显示 0 个手势段。

### 7.2 为什么启动时报端口占用？

说明已经有一个后端服务占用了 `8000` 端口。可以直接使用已有服务，或停止旧进程后重新启动。

查看占用端口的进程：

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object LocalAddress,LocalPort,State,OwningProcess
```

停止进程：

```powershell
Stop-Process -Id 进程ID
```

### 7.3 PyTorch 的 FutureWarning 是否影响运行？

不影响。这是 `torch.load` 关于未来版本安全策略变化的提醒，不是启动失败原因。

### 7.4 为什么 CPU 模式比较慢？

当前模型包含姿态估计网络和 LSTM，视频需要逐帧或采样帧进行推理。CPU 模式稳定性更好，但速度会慢于 GPU。当前阶段以验证模型可用性为主，因此默认使用 CPU。

## 8. 后续优化方向

- 增加前端上传进度和后端推理进度反馈。
- 支持用户选择采样频率，例如快速模式、标准模式、精细模式。
- 对长视频增加异步任务机制，避免 HTTP 请求长时间等待。
- 排查 CUDA 环境兼容性，恢复稳定 GPU 推理。
- 增加手势识别结果导出功能。
- 对不同视频场景进行更多测试，评估模型准确率和鲁棒性。

