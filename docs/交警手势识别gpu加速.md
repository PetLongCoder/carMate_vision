# 交警手势识别功能他人电脑运行教程

本文档用于指导其他同学在自己的电脑上运行 carMate Vision 项目的交警手势识别功能，包括后端、前端、GPU 配置、视频上传识别和实时摄像头识别。

## 1. 运行前准备

### 1.1 必需软件

请先安装：

| 软件 | 建议版本 | 用途 |
| --- | --- | --- |
| Git | 任意较新版本 | 拉取项目代码 |
| Python | 3.10 或 3.11 | 运行后端服务 |
| Node.js | 20 或更高 | 运行前端页面 |
| 浏览器 | Chrome / Edge | 打开 Web 页面 |

如果需要使用 GPU，还需要：

| 软件/硬件 | 说明 |
| --- | --- |
| NVIDIA 显卡 | 只有 NVIDIA 显卡支持 CUDA 推理 |
| NVIDIA 显卡驱动 | 需要能正常运行 `nvidia-smi` |
| CUDA 版 PyTorch | 后端模型使用 PyTorch 推理 |

## 2. 拉取项目代码

打开 PowerShell 或终端，进入你希望存放项目的目录，例如：

```powershell
cd D:\code
```

拉取仓库：

```powershell
git clone https://github.com/PetLongCoder/carMate_vision.git
cd carMate_vision
```

如果已经有项目代码，进入项目目录后更新代码：

```powershell
git pull origin main
```

## 3. 后端环境配置

进入后端目录：

```powershell
cd backend
```

建议创建虚拟环境：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\activate
```

升级 pip：

```powershell
python -m pip install --upgrade pip
```

## 4. 安装后端依赖

### 4.1 不使用 GPU 的普通安装方式

如果电脑没有 NVIDIA 显卡，或者只想先跑通功能，可以直接安装：

```powershell
pip install -r requirements.txt
```

这种方式可能安装 CPU 版 PyTorch，视频分析速度会比较慢，但功能可以运行。

### 4.2 使用 GPU 的安装方式

如果电脑有 NVIDIA 显卡，建议安装 CUDA 版 PyTorch。

先检查显卡驱动是否可用：

```powershell
nvidia-smi
```

如果能看到 NVIDIA 显卡名称、驱动版本和显存信息，说明驱动基本可用。

然后安装项目依赖：

```powershell
pip install -r requirements.txt
```

如果安装后发现 PyTorch 不是 CUDA 版，可以重新安装 CUDA 版 PyTorch：

```powershell
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

安装完成后检查 PyTorch 是否能使用 CUDA：

```powershell
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

如果输出：

```text
True
NVIDIA ...
```

说明 GPU 可用。

如果输出：

```text
False
CPU
```

说明当前 Python 环境没有成功使用 CUDA。

## 5. 后端配置文件

后端配置示例文件是：

```text
backend/.env.example
```

第一次运行时，复制一份为 `.env`：

```powershell
copy .env.example .env
```

重点关注交警手势识别配置：

```env
CARMATE_DEVICE=auto
CARMATE_VIDEO_SAMPLE_FPS=15
CARMATE_LSTM_WARMUP_FRAMES=15
CARMATE_SMOOTH_WINDOW=5
CARMATE_MIN_SEGMENT_SECONDS=0.6
CARMATE_LABEL_TIME_OFFSET_SECONDS=0.8
```

### 5.1 GPU/CPU 配置说明

`CARMATE_DEVICE` 有三个可选值：

| 值 | 说明 |
| --- | --- |
| auto | 推荐。有 CUDA GPU 就使用 GPU，否则自动回退 CPU |
| cuda | 强制使用 GPU；如果 CUDA 不可用，后端会启动失败 |
| cpu | 强制使用 CPU |

推荐其他同学使用：

```env
CARMATE_DEVICE=auto
```

如果确定电脑已经配置好 CUDA，也可以使用：

```env
CARMATE_DEVICE=cuda
```

## 6. 模型文件说明

交警手势识别模型文件已经放在项目中：

```text
backend/ctpgr/checkpoints/pose_model.pt
backend/ctpgr/checkpoints/lstm.pt
```

正常情况下不需要再去云盘手动下载模型。

如果启动后端时报模型文件不存在，请检查上述两个文件是否存在。

## 7. 启动后端服务

在 `backend` 目录下运行：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

正常启动后，浏览器访问：

```text
http://localhost:8000/api/health
```

如果看到类似结果：

```json
{
  "status": "ok",
  "model": "ctpgr-pytorch (Pose + LSTM)",
  "classes": 9,
  "device": "cuda",
  "cuda_available": true,
  "gpu_name": "NVIDIA GeForce RTX 4070 Laptop GPU"
}
```

说明后端已启动，并且正在使用 GPU。

如果看到：

```json
"device": "cpu"
```

说明当前后端正在使用 CPU。

## 8. 前端环境配置

打开新的 PowerShell 终端，进入前端目录：

```powershell
cd frontend
```

安装前端依赖：

```powershell
npm install
```

启动前端：

```powershell
npm.cmd run dev
```

浏览器访问：

```text
http://localhost:5173
```

如果前端请求地址需要手动配置，可以在 `frontend` 目录下创建 `.env`：

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

## 9. 测试上传视频识别

进入前端页面后：

1. 打开“交警手势识别”功能页面。
2. 点击“选择视频文件”。
3. 上传交警手势测试视频。
4. 页面会先显示视频预览。
5. 后端开始进行 LSTM 时序分析。
6. 视频上会叠加当前动作标签。
7. 分析完成后，会显示：
   - 当前播放位置动作
   - 识别到的动作段数量
   - 主要动作
   - 动作分布
   - 视频动作时间线

支持的视频格式包括：

```text
MP4、AVI、MOV、WebM、MKV
```

如果原视频浏览器不能直接播放，后端会自动生成浏览器兼容的 MP4 预览，不需要手动转码。

## 10. 测试实时摄像头识别

在“交警手势识别”页面：

1. 点击“实时摄像头”。
2. 浏览器弹出权限提示时选择允许。
3. 页面显示摄像头实时画面。
4. 在摄像头前做交警手势。
5. 页面会显示当前识别动作和置信度。
6. 点击“停止摄像头”结束实时识别。

当前实时摄像头实现方式是：

```text
前端定时从摄像头画面截帧 → 上传到后端 → 后端保持 LSTM 状态 → 返回当前手势
```

它可以用于实时演示，但不是 WebRTC/RTSP 那种高帧率连续视频流。

## 11. 如何确认自己是否正在使用 GPU

最可靠的方法是访问：

```text
http://localhost:8000/api/health
```

如果返回：

```json
"cuda_available": true,
"device": "cuda",
"gpu_name": "NVIDIA ..."
```

说明正在使用 GPU。

也可以在分析视频时打开任务管理器，查看 GPU 使用率是否上升。

如果返回：

```json
"device": "cpu"
```

说明没有用上 GPU。常见原因：

- 电脑没有 NVIDIA 显卡。
- 没有安装 NVIDIA 驱动。
- `nvidia-smi` 不可用。
- 安装的是 CPU 版 PyTorch。
- `.env` 中配置了 `CARMATE_DEVICE=cpu`。
- CUDA 版 PyTorch 与驱动版本不兼容。

## 12. 常见问题

### 12.1 后端启动时报找不到模型

检查文件是否存在：

```text
backend/ctpgr/checkpoints/pose_model.pt
backend/ctpgr/checkpoints/lstm.pt
```

如果不存在，请重新拉取最新仓库。

### 12.2 视频可以分析但浏览器不能播放

这是视频编码兼容问题。当前项目已经支持自动预览转码。

如果仍然失败，确认后端依赖中有：

```text
imageio-ffmpeg
```

可以重新安装依赖：

```powershell
pip install -r requirements.txt
```

### 12.3 分析速度很慢

优先检查是否在使用 GPU：

```text
http://localhost:8000/api/health
```

如果是 CPU，长视频分析会比较慢。

如果已经是 GPU，但仍然很慢，可以适当降低 `.env` 中的视频采样帧率：

```env
CARMATE_VIDEO_SAMPLE_FPS=8
```

采样帧率越高，识别越细，但速度越慢。

### 12.4 实时摄像头没有画面

检查：

- 浏览器是否允许摄像头权限。
- 摄像头是否被其他软件占用。
- 是否使用 Chrome 或 Edge。
- 页面是否通过 `localhost` 打开。

### 12.5 强制 GPU 后后端启动失败

如果 `.env` 中设置了：

```env
CARMATE_DEVICE=cuda
```

但 CUDA 环境不可用，后端会启动失败。

可以改为：

```env
CARMATE_DEVICE=auto
```

或者：

```env
CARMATE_DEVICE=cpu
```

## 13. 推荐运行命令汇总

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端

```powershell
cd frontend
npm install
npm.cmd run dev
```

### GPU 版 PyTorch

```powershell
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 检查 GPU

```powershell
nvidia-smi
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

### 检查后端运行状态

```text
http://localhost:8000/api/health
```

## 14. 结论

其他人在自己的电脑上运行该功能时，只要完成依赖安装并启动后端、前端，就可以使用交警手势识别。

如果电脑具备 NVIDIA 显卡，并正确安装 CUDA 版 PyTorch，同时 `.env` 中设置：

```env
CARMATE_DEVICE=auto
```

或：

```env
CARMATE_DEVICE=cuda
```

后端分析视频时就会使用 GPU。

如果没有 GPU 或 CUDA 环境不可用，项目会在 `auto` 模式下回退到 CPU，功能仍可运行，但视频分析速度会变慢。
