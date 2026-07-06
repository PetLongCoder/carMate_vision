# 交警手势识别功能他人电脑运行指南

## 1. 适用场景

本文档用于指导其他成员在自己的电脑上拉取项目代码，并运行交警手势识别功能。

交警手势识别功能已经合并到 GitHub 仓库 `main` 分支，但模型权重文件没有上传到 GitHub，因此其他电脑首次运行前需要手动补充模型文件。

## 2. 需要准备的软件

建议环境：

- Windows 10 或 Windows 11
- Python 3.10 或 3.11
- Node.js 18 或更高版本
- Git

检查命令：

```powershell
python --version
node --version
npm --version
git --version
```

如果以上命令有任意一个无法识别，需要先安装对应软件。

## 3. 拉取项目代码

在合适的工作目录执行：

```powershell
git clone https://github.com/PetLongCoder/carMate_vision.git
cd carMate_vision
git checkout main
```

如果本地已经 clone 过项目，则执行：

```powershell
cd D:\code\carMate_vision\carMate_vision
git checkout main
git pull origin main
```

## 4. 补充模型权重文件

交警手势识别依赖 `ctpgr-pytorch` 的两个预训练模型文件：

```text
pose_model.pt
lstm.pt
```

由于文件较大，GitHub 仓库中不会包含它们。需要从项目负责人或共享网盘获取这两个文件。

获取后放到：

```text
backend/ctpgr/checkpoints/
```

最终目录结构应为：

```text
backend/ctpgr/checkpoints/
├── README.md
├── pose_model.pt
└── lstm.pt
```

如果没有这个目录，可以手动创建：

```powershell
mkdir backend\ctpgr\checkpoints
```

然后把 `pose_model.pt` 和 `lstm.pt` 复制进去。

## 5. 安装后端依赖

进入后端目录：

```powershell
cd backend
```

建议创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

安装依赖：

```powershell
pip install -r requirements.txt
```

如果安装速度较慢，可以使用国内镜像：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 6. 启动后端服务

在 `backend` 目录下执行：

```powershell
python server.py
```

启动成功时应看到类似日志：

```text
模型预加载完成
CarMate 推理服务已启动 (ctpgr-pytorch)
Uvicorn running on http://0.0.0.0:8000
```

保持这个终端窗口不要关闭。

## 7. 检查后端是否可用

新开一个 PowerShell，执行：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

正常返回示例：

```json
{
  "status": "ok",
  "model": "ctpgr-pytorch (Pose + LSTM)",
  "classes": 9,
  "device": "cpu",
  "device_mode": "cpu"
}
```

如果返回 `status: ok`，说明后端启动成功。

## 8. 安装并启动前端

打开新的 PowerShell，进入前端目录：

```powershell
cd frontend
```

首次运行需要安装依赖：

```powershell
npm install
```

启动前端：

```powershell
npm.cmd run dev
```

终端会输出访问地址，通常是：

```text
http://localhost:5173
```

在浏览器打开该地址，进入“交警手势识别”页面即可上传视频测试。

## 9. 推荐测试方式

首次测试建议使用 20 到 60 秒的视频片段。

不建议第一次就上传完整长视频，原因是：

- 当前默认使用 CPU 推理，速度较慢。
- 视频识别需要逐帧或按采样帧进行姿态估计和 LSTM 推理。
- 长视频可能需要几分钟才能返回结果。

## 10. CPU 和 GPU 模式说明

当前后端默认使用 CPU 模式，稳定性较好：

```powershell
python server.py
```

如果电脑已经正确安装 CUDA、显卡驱动和 GPU 版本 PyTorch，可以尝试 GPU 模式：

```powershell
$env:CARMATE_DEVICE="cuda"
python server.py
```

如果 GPU 模式出现 `python.exe - 应用程序错误` 或程序直接崩溃，说明当前电脑的 CUDA/PyTorch/驱动组合不稳定，建议继续使用 CPU 模式。

## 11. 常见问题

### 11.1 启动后端时报找不到模型文件

检查以下文件是否存在：

```text
backend/ctpgr/checkpoints/pose_model.pt
backend/ctpgr/checkpoints/lstm.pt
```

如果不存在，需要重新复制模型权重文件。

### 11.2 启动后端时报 8000 端口被占用

报错示例：

```text
[Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000)
```

说明已经有后端服务占用了 `8000` 端口。

可以先检查现有后端是否可用：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

如果需要关闭占用端口的进程：

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object LocalAddress,LocalPort,State,OwningProcess
Stop-Process -Id 进程ID
```

### 11.3 前端提示无法连接后端

请确认：

- 后端终端仍在运行。
- 后端地址是 `http://localhost:8000`。
- 健康检查接口 `http://127.0.0.1:8000/api/health` 能正常返回。

### 11.4 上传视频后识别很慢

这是正常现象，尤其在 CPU 模式下。建议先用短视频测试。

### 11.5 显示 0 个手势段

`gestureId=0` 表示“无手势”。如果模型大部分采样帧判断为无手势，前端就会显示 0 个手势段。

## 12. 最小运行清单

其他成员只要完成以下事项，就可以运行交警手势识别功能：

1. 拉取 GitHub `main` 分支最新代码。
2. 把 `pose_model.pt` 和 `lstm.pt` 放到 `backend/ctpgr/checkpoints/`。
3. 后端执行 `pip install -r requirements.txt`。
4. 后端执行 `python server.py`。
5. 前端执行 `npm install`。
6. 前端执行 `npm.cmd run dev`。
7. 浏览器打开前端页面并上传短视频测试。

