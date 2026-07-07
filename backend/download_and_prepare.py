"""
步骤1: 下载 ChineseTrafficPolicePose 数据集并转换为 YOLO 分类格式

数据集来源: https://github.com/zc402/ChineseTrafficPolicePose
Google Drive: https://drive.google.com/drive/folders/13KHZpweTE1vRGAMF7wqMDE35kDw40Uym

输出结构:
  dataset/
    train/
      stop/          # 停止
      move_straight/ # 直行
      left_turn/     # 左转
      right_turn/    # 右转
      left_turn_waiting/  # 左转待转
      lane_changing/ # 变道
      slow_down/     # 减速慢行
      pull_over/     # 靠边停车
    val/
      (同上)
"""

import os
import sys
import csv
import cv2
import shutil
from pathlib import Path
from sklearn.model_selection import train_test_split

# ---- 配置 ----
PROJECT_ROOT = Path(__file__).parent
DATASET_DIR = PROJECT_ROOT / "ChineseTrafficPolicePose"
FRAMES_DIR = PROJECT_ROOT / "frames"
YOLO_DATASET_DIR = PROJECT_ROOT / "dataset"

# 8 种交警手势类别 (与前端 PoliceGesture.tsx 中 GESTURE_LABELS 对应)
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

# 中文到英文的映射
CN_TO_EN = {
    "停止": "stop",
    "直行": "move_straight",
    "左转": "left_turn",
    "右转": "right_turn",
    "左转待转": "left_turn_waiting",
    "变道": "lane_changing",
    "减速慢行": "slow_down",
    "靠边停车": "pull_over",
}

# 训练集比例
TRAIN_RATIO = 0.8
# 每隔多少帧采样一次 (避免相似帧过多)
FRAME_SKIP = 5


def download_dataset():
    """通过 gdown 下载数据集 (需要网络访问 Google Drive)"""
    drive_url = "https://drive.google.com/drive/folders/13KHZpweTE1vRGAMF7wqMDE35kDw40Uym"

    print("=" * 60)
    print("下载 ChineseTrafficPolicePose 数据集")
    print("=" * 60)

    if DATASET_DIR.exists() and any(DATASET_DIR.iterdir()):
        print(f"[INFO] 数据集目录已存在: {DATASET_DIR}")
        print("[INFO] 跳过下载。如需重新下载，请删除该目录后重试。")
        return True

    try:
        import gdown
        print(f"[INFO] 正在下载到: {DATASET_DIR}")
        # gdown 下载整个文件夹
        gdown.download_folder(url=drive_url, output=str(DATASET_DIR), quiet=False)
        print("[OK] 下载完成!")
        return True
    except ImportError:
        print("[ERROR] 请先安装 gdown: pip install gdown")
        return False
    except Exception as e:
        print(f"[WARN] gdown 下载失败: {e}")
        print(f"[INFO] 请手动下载数据集并解压到: {DATASET_DIR}")
        print(f"[INFO] 下载地址: {drive_url}")
        return False


# CSV 中的数字标签 1-8 到类别名的映射
# (参考 ChineseTrafficPolicePose 数据集定义)
CSV_LABEL_MAP = {
    1: "stop",              # 停止
    2: "move_straight",     # 直行
    3: "left_turn",         # 左转
    4: "right_turn",        # 右转
    5: "left_turn_waiting", # 左转待转
    6: "lane_changing",     # 变道
    7: "slow_down",         # 减速慢行
    8: "pull_over",         # 靠边停车
}


def parse_csv_labels(csv_path):
    """解析 ChineseTrafficPolicePose CSV 标注文件

    CSV 格式: 单行逗号分隔的数字, 每帧一个值
    0 = 背景/过渡, 1-8 = 8 种手势类别
    """
    with open(csv_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    labels = []
    for val in content.split(","):
        val = val.strip()
        if val:
            try:
                labels.append(int(val))
            except ValueError:
                labels.append(0)
    return labels


def extract_frames_from_videos():
    """从视频中提取帧并标注"""
    print("\n" + "=" * 60)
    print("从视频中提取帧 (CSV 单行标注格式)")
    print("=" * 60)

    if not DATASET_DIR.exists():
        print(f"[ERROR] 数据集目录不存在: {DATASET_DIR}")
        return False

    # 查找视频文件和对应的 CSV 标注
    video_files = sorted(list(DATASET_DIR.rglob("*.mp4")) + list(DATASET_DIR.rglob("*.MP4")))

    print(f"[INFO] 找到 {len(video_files)} 个视频文件")

    if not video_files:
        print("[WARN] 未找到视频文件。")
        return False

    # 清理旧的帧目录
    if FRAMES_DIR.exists():
        shutil.rmtree(FRAMES_DIR)

    total_frames = 0

    for video_path in video_files:
        video_name = video_path.stem  # 例如: "001", "003", ...
        # 找到同名的 CSV 文件
        csv_path = video_path.with_suffix(".csv")

        if not csv_path.exists():
            print(f"[WARN] {video_name}: 无对应 CSV 标注文件, 跳过")
            continue

        # 解析 CSV 标签
        frame_labels = parse_csv_labels(csv_path)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"[WARN] 无法打开视频: {video_name}")
            continue

        video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"\n[INFO] 处理: {video_name}.mp4 ({video_frames} 帧, {len(frame_labels)} 个标签)")

        frame_idx = 0
        saved = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 每 FRAME_SKIP 帧采样
            if frame_idx % FRAME_SKIP == 0 and frame_idx < len(frame_labels):
                label_id = frame_labels[frame_idx]
                if label_id > 0 and label_id in CSV_LABEL_MAP:
                    class_name = CSV_LABEL_MAP[label_id]
                    class_dir = FRAMES_DIR / class_name
                    class_dir.mkdir(parents=True, exist_ok=True)
                    out_path = class_dir / f"{video_name}_f{frame_idx:06d}.jpg"
                    cv2.imwrite(str(out_path), frame)
                    saved += 1
                    total_frames += 1

            frame_idx += 1

        cap.release()
        print(f"  -> 保存 {saved} 帧 (跳过 {FRAME_SKIP}x 降采样)")

    print(f"\n[OK] 总共提取 {total_frames} 帧到 {FRAMES_DIR}")

    # 打印每个类别的统计
    for cls_name in CLASS_NAMES:
        cls_dir = FRAMES_DIR / cls_name
        count = len(list(cls_dir.glob("*"))) if cls_dir.exists() else 0
        print(f"  {cls_name}: {count} 帧")

    return total_frames > 0


def organize_dataset():
    """将帧按类别组织成 YOLO 分类训练格式 (train/val 分割)"""
    print("\n" + "=" * 60)
    print("组织数据集为 YOLO 分类格式")
    print("=" * 60)

    if not FRAMES_DIR.exists() or not any(FRAMES_DIR.iterdir()):
        print(f"[ERROR] 帧目录为空: {FRAMES_DIR}")
        print("[INFO] 如果无法从视频提取帧，将使用数据增强生成模拟数据...")
        return generate_synthetic_data()

    # 清理旧的 YOLO 数据集目录
    if YOLO_DATASET_DIR.exists():
        shutil.rmtree(YOLO_DATASET_DIR)

    for split in ["train", "val"]:
        for cls_name in CLASS_NAMES:
            (YOLO_DATASET_DIR / split / cls_name).mkdir(parents=True, exist_ok=True)

    # 对每个类别进行 train/val 分割
    for cls_name in CLASS_NAMES:
        cls_dir = FRAMES_DIR / cls_name
        if not cls_dir.exists():
            print(f"[WARN] 类别目录为空: {cls_dir}")
            continue

        images = list(cls_dir.glob("*.jpg")) + list(cls_dir.glob("*.png"))
        if len(images) == 0:
            continue

        train_imgs, val_imgs = train_test_split(images, test_size=1 - TRAIN_RATIO, random_state=42)

        for img_path in train_imgs:
            dest = YOLO_DATASET_DIR / "train" / cls_name / img_path.name
            shutil.copy2(img_path, dest)

        for img_path in val_imgs:
            dest = YOLO_DATASET_DIR / "val" / cls_name / img_path.name
            shutil.copy2(img_path, dest)

        print(f"[INFO] {cls_name}: train={len(train_imgs)}, val={len(val_imgs)}")

    return True


def generate_synthetic_data():
    """
    无法获取视频数据集时的回退方案：
    使用 MediaPipe + 数据增强生成模拟训练数据
    这样至少可以跑通训练流程，后续替换为真实数据时只需替换 dataset/ 目录
    """
    print("\n[INFO] 生成占位数据集 (用于验证训练流程)")
    print("[INFO] 你需要替换 dataset/ 目录为真实标注数据")

    if YOLO_DATASET_DIR.exists():
        shutil.rmtree(YOLO_DATASET_DIR)

    import numpy as np

    for split, count in [("train", 50), ("val", 10)]:
        for cls_name in CLASS_NAMES:
            cls_dir = YOLO_DATASET_DIR / split / cls_name
            cls_dir.mkdir(parents=True, exist_ok=True)

            for i in range(count):
                # 生成随机彩色占位图 (640x640)
                img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
                # 在图片上叠加类别文字
                cv2.putText(img, cls_name, (100, 320), cv2.FONT_HERSHEY_SIMPLEX,
                            2, (255, 255, 255), 3)
                cv2.putText(img, f"sample_{i}", (100, 400), cv2.FONT_HERSHEY_SIMPLEX,
                            1, (200, 200, 200), 2)

                out_path = cls_dir / f"sample_{i:04d}.jpg"
                cv2.imwrite(str(out_path), img)

    print("[OK] 占位数据集已生成。请替换为真实标注数据后重新训练。")
    return True


def main():
    print("=" * 60)
    print("CarMate 交警手势数据集准备工具")
    print("=" * 60)
    print(f"类别 ({len(CLASS_NAMES)}): {CLASS_NAMES}")
    print()

    # 步骤1: 尝试下载数据集
    success = download_dataset()

    # 步骤2: 提取帧
    if success and DATASET_DIR.exists():
        success = extract_frames_from_videos()

    # 步骤3: 组织数据集
    if not success or not FRAMES_DIR.exists() or not any(FRAMES_DIR.iterdir()):
        print("\n[WARN] 无法从视频获取帧数据，切换到合成数据模式...")
        organize_dataset()
    else:
        organize_dataset()

    # 打印最终统计
    print("\n" + "=" * 60)
    print("数据集准备完成!")
    print("=" * 60)

    for split in ["train", "val"]:
        split_dir = YOLO_DATASET_DIR / split
        if split_dir.exists():
            total = sum(1 for _ in split_dir.rglob("*.jpg"))
            total += sum(1 for _ in split_dir.rglob("*.png"))
            print(f"  {split}: {total} 张图片")
            for cls_name in CLASS_NAMES:
                cls_dir = split_dir / cls_name
                if cls_dir.exists():
                    count = len(list(cls_dir.glob("*")))
                    print(f"    {cls_name}: {count}")

    print(f"\n下一步: python train.py")


if __name__ == "__main__":
    main()
