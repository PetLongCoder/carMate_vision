# CTPGR 模型权重

交警手势识别后端启动时会加载下面两个预训练权重：

```text
backend/ctpgr/checkpoints/pose_model.pt
backend/ctpgr/checkpoints/lstm.pt
```

这两个文件已经随仓库提交。其他成员 clone 项目后，不需要再去云盘单独下载模型文件。

目录结构应为：

```text
backend/ctpgr/checkpoints/
├── README.md
├── pose_model.pt
└── lstm.pt
```

如果后端启动时报缺少模型文件，请先确认当前目录下这两个 `.pt` 文件是否存在。
