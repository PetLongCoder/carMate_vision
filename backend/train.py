"""
步骤2: 训练 YOLOv11-cls 交警手势分类模型

使用 Ultralytics YOLO 分类模式训练 8 种交警手势识别模型。

用法:
  python train.py              # 使用默认参数训练 (yolo11n-cls.pt)
  python train.py --epochs 200 # 自定义训练轮数
  python train.py --model yolov8n-cls.pt  # 使用旧版 YOLOv8
"""

import argparse
import sys
from pathlib import Path
from ultralytics import YOLO

# ---- 配置 ----
PROJECT_ROOT = Path(__file__).parent
DATASET_DIR = PROJECT_ROOT / "dataset"
MODELS_DIR = PROJECT_ROOT / "models"

# 8 种交警手势类别 (与前端保持一致)
CLASS_NAMES = [
    "stop",              # 0: 停止
    "move_straight",     # 1: 直行
    "left_turn",         # 2: 左转
    "right_turn",        # 3: 右转
    "left_turn_waiting", # 4: 左转待转
    "lane_changing",     # 5: 变道
    "slow_down",         # 6: 减速慢行
    "pull_over",         # 7: 靠边停车
]


def check_dataset():
    """检查数据集是否就绪"""
    train_dir = DATASET_DIR / "train"
    val_dir = DATASET_DIR / "val"

    if not train_dir.exists():
        print(f"[ERROR] 训练集目录不存在: {train_dir}")
        print("[INFO] 请先运行: python download_and_prepare.py")
        return False

    train_count = sum(1 for _ in train_dir.rglob("*.jpg")) + \
                  sum(1 for _ in train_dir.rglob("*.png"))
    val_count = sum(1 for _ in val_dir.rglob("*.jpg")) + \
                sum(1 for _ in val_dir.rglob("*.png")) if val_dir.exists() else 0

    print(f"[INFO] 训练集: {train_count} 张, 验证集: {val_count} 张")

    if train_count == 0:
        print("[ERROR] 训练集为空!")
        return False

    return True


def train(args):
    """训练 YOLO 分类模型"""
    if not check_dataset():
        sys.exit(1)

    MODELS_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("CarMate 交警手势识别 - 模型训练")
    print("=" * 60)
    print(f"模型: {args.model}")
    print(f"轮数: {args.epochs}")
    print(f"分辨率: {args.imgsz}")
    print(f"批量: {args.batch}")
    print(f"设备: {args.device}")
    print(f"类别数: {len(CLASS_NAMES)}")
    print("=" * 60)

    # 加载预训练模型
    model = YOLO(args.model)

    # 训练
    results = model.train(
        data=str(DATASET_DIR),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        lr0=args.lr,
        dropout=args.dropout,
        optimizer=args.optimizer,
        patience=args.patience,
        name="carMate_gesture",
        exist_ok=True,
        verbose=True,
    )

    # 导出 ONNX 模型 (用于部署)
    best_pt = MODELS_DIR / "carMate_gesture.pt"
    best_onnx = MODELS_DIR / "carMate_gesture.onnx"

    # 复制最佳模型到 models/ 目录
    import shutil
    run_dir = Path(results.save_dir)
    weights_file = run_dir / "weights" / "best.pt"
    if weights_file.exists():
        shutil.copy2(weights_file, best_pt)
        print(f"\n[OK] 模型已保存: {best_pt}")

        # 导出 ONNX
        model = YOLO(str(best_pt))
        model.export(format="onnx", imgsz=args.imgsz)
        onnx_src = run_dir / "weights" / "best.onnx"
        if onnx_src.exists():
            shutil.copy2(onnx_src, best_onnx)
            print(f"[OK] ONNX 模型已保存: {best_onnx}")

    # 输出类别映射 (供推理服务使用)
    print("\n" + "=" * 60)
    print("训练完成! 类别映射:")
    for i, name in enumerate(CLASS_NAMES):
        print(f"  {i}: {name}")
    print(f"\n模型文件: {best_pt}")
    print(f"ONNX 文件: {best_onnx}")
    print(f"\n下一步: python server.py 启动推理服务")

    return results


def main():
    parser = argparse.ArgumentParser(description="训练交警手势识别模型")

    # 模型选择
    parser.add_argument("--model", type=str, default="yolo11n-cls.pt",
                        choices=["yolo11n-cls.pt", "yolo11s-cls.pt", "yolo11m-cls.pt",
                                 "yolo11l-cls.pt", "yolov8n-cls.pt", "yolov8s-cls.pt",
                                 "yolov8m-cls.pt"],
                        help="预训练分类模型 (默认: yolo11n-cls.pt)")

    # 训练参数
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数 (默认: 100)")
    parser.add_argument("--imgsz", type=int, default=640, help="图片分辨率 (默认: 640)")
    parser.add_argument("--batch", type=int, default=16, help="批量大小 (默认: 16, 显存不足则减小)")
    parser.add_argument("--lr", type=float, default=0.01, help="学习率 (默认: 0.01)")
    parser.add_argument("--dropout", type=float, default=0.2, help="Dropout 比例 (默认: 0.2)")
    parser.add_argument("--patience", type=int, default=20, help="早停轮数 (默认: 20)")
    parser.add_argument("--optimizer", type=str, default="auto", help="优化器 (默认: auto)")
    parser.add_argument("--workers", type=int, default=4, help="数据加载线程 (默认: 4)")
    parser.add_argument("--device", type=str, default="auto",
                        help="训练设备: auto(自动), cpu, 0(GPU), mps(Mac)")

    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
