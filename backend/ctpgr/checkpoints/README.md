# CTPGR 模型权重放置说明

交警手势识别后端启动时需要以下两个模型权重文件：

```text
backend/ctpgr/checkpoints/pose_model.pt
backend/ctpgr/checkpoints/lstm.pt
```

这两个文件体积较大，不提交到 GitHub。其他成员 clone 项目后，需要手动从项目负责人或共享网盘获取这两个文件，并放到当前目录。

放置完成后的目录结构应为：

```text
backend/ctpgr/checkpoints/
├── README.md
├── pose_model.pt
└── lstm.pt
```

缺少权重文件时，后端会在启动模型预加载阶段失败，交警手势识别功能无法使用。

