"""
FFmpeg 推流服务 (stream_pusher)
================================

将 OpenCV 标注帧通过 FFmpeg 子进程推送到 MediaMTX 流媒体服务器。

集成到现有流媒体追踪流程:
  1. POST /api/plate/stream/start?push_enabled=true
  2. video_processor._run_stream_loop() 每次获得标注帧后调用 pusher.write_frame()
  3. pusher 通过 stdin 管道送入 FFmpeg → H.264 编码 → RTSP 推流到 MediaMTX
  4. MediaMTX 自动提供服务 (HLS/WebRTC/RTSP/RTMP)

架构:
  Python 侧:   frame (BGR ndarray) → .tobytes() → stdin pipe
  FFmpeg 侧:   stdin(rawvideo) → libx264 编码 → RTSP/RTMP 推流

依赖:
  - 本地安装 FFmpeg (或通过 imageio-ffmpeg 自动获取)
  - MediaMTX (或任意支持 RTSP publish 的流媒体服务器)

参考:
  - 沙盘摄像头获取_识别推流.pdf — 实时识别+推送方案
  - MediaMTX: https://github.com/bluenviron/mediamtx
"""
import os
import sys
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.utils.logger import logger


# ─── 默认推流参数 ───────────────────────────────────
DEFAULT_FPS = 25
DEFAULT_BITRATE = "2M"
DEFAULT_PRESET = "ultrafast"
DEFAULT_TUNE = "zerolatency"


def _resolve_ffmpeg() -> Optional[str]:
    """查找可用的 FFmpeg 可执行文件路径。

    优先顺序:
      1. 环境变量 CARMATE_FFMPEG_PATH
      2. 系统 PATH 中的 ffmpeg
      3. imageio_ffmpeg 捆绑的 ffmpeg
    """
    ffmpeg_bin = os.getenv("CARMATE_FFMPEG_PATH")
    if ffmpeg_bin and Path(ffmpeg_bin).is_file():
        return ffmpeg_bin

    system_ffmpeg = subprocess.run(
        ["where", "ffmpeg"], capture_output=True, text=True
    )
    if system_ffmpeg.returncode == 0:
        path = system_ffmpeg.stdout.strip().split("\n")[0].strip()
        if path:
            return path

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class FFmpegPusher:
    """
    FFmpeg 推流器

    将 OpenCV BGR 帧通过管道送入 FFmpeg 子进程, 编码为 H.264 并推送到
    目标 RTSP/RTMP 地址。

    用法:
        pusher = FFmpegPusher(dst_url="rtsp://localhost:8554/recognized/cam1")
        pusher.start(width=1920, height=1080, fps=25)

        for frame in frames:
            pusher.write_frame(frame)   # BGR ndarray

        pusher.stop()

    线程安全: write_frame 可从任意线程调用 (内部通过 stdin 写锁保护)。
    """

    def __init__(
        self,
        dst_url: str,
        fps: int = DEFAULT_FPS,
        bitrate: str = DEFAULT_BITRATE,
        preset: str = DEFAULT_PRESET,
        tune: str = DEFAULT_TUNE,
        ffmpeg_bin: Optional[str] = None,
        timeout: int = 10,
    ):
        """
        Args:
            dst_url:  推流目标地址, 如 rtsp://localhost:8554/recognized/cam1
            fps:      输出帧率 (默认 25)
            bitrate:  编码码率 (默认 "2M")
            preset:   x264 preset (默认 "ultrafast")
            tune:     x264 tune (默认 "zerolatency")
            ffmpeg_bin: FFmpeg 路径, 为 None 则自动查找
            timeout:  子进程启动超时秒数
        """
        self.dst_url = dst_url
        self.fps = fps
        self.bitrate = bitrate
        self.preset = preset
        self.tune = tune
        self.timeout = timeout

        self._ffmpeg_bin = ffmpeg_bin or _resolve_ffmpeg()
        if not self._ffmpeg_bin:
            raise RuntimeError(
                "未找到 FFmpeg。请安装 ffmpeg 并将其加入 PATH, "
                "或安装 imageio-ffmpeg (pip install imageio-ffmpeg) 后重试。"
            )

        self._proc: Optional[subprocess.Popen] = None
        self._width: int = 0
        self._height: int = 0
        self._running = False
        self._lock = threading.Lock()

        # 统计
        self.frames_pushed: int = 0
        self.start_time: float = 0.0

    # ── 属性 ────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running and self._proc is not None and self._proc.poll() is None

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time if self.start_time > 0 else 0.0

    # ── 生命周期 ────────────────────────────────────

    def start(self, width: int, height: int) -> bool:
        """
        启动 FFmpeg 子进程.

        Args:
            width:  输入帧宽度
            height: 输入帧高度

        Returns:
            True 表示启动成功, False 表示失败
        """
        if self.is_running:
            logger.warning("FFmpegPusher 已在运行, 忽略重复启动")
            return True

        self._width = width
        self._height = height
        self.frames_pushed = 0

        command = self._build_command()

        logger.info(
            "启动 FFmpeg 推流: %sx%d@%d → %s",
            width, height, self.fps, self.dst_url
        )
        logger.debug("FFmpeg 命令: %s", " ".join(command))

        try:
            self._proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error("FFmpeg 可执行文件不存在: %s", self._ffmpeg_bin)
            return False
        except Exception as exc:
            logger.error("启动 FFmpeg 失败: %s", exc)
            return False

        # 等待子进程稳定
        time.sleep(0.5)
        if self._proc.poll() is not None:
            stderr = self._try_read_stderr()
            logger.error(
                "FFmpeg 启动后立即退出 (rc=%d): %s",
                self._proc.returncode, stderr
            )
            return False

        self._running = True
        self.start_time = time.time()
        logger.info("FFmpeg 推流已启动 (PID=%d)", self._proc.pid)
        return True

    def write_frame(self, frame: np.ndarray) -> bool:
        """
        写入一帧到 FFmpeg 子进程的 stdin.

        Args:
            frame: BGR 格式的 OpenCV ndarray

        Returns:
            True 表示写入成功, False 表示管道已断开
        """
        if not self.is_running:
            return False

        try:
            with self._lock:
                if self._proc is None or self._proc.stdin is None:
                    return False
                self._proc.stdin.write(frame.tobytes())
                self._proc.stdin.flush()
            self.frames_pushed += 1
            return True
        except BrokenPipeError:
            logger.warning("FFmpeg 管道断开 (BrokenPipe), 推流中断")
            self._running = False
            return False
        except OSError as exc:
            logger.warning("FFmpeg 写入异常: %s", exc)
            self._running = False
            return False

    def stop(self, timeout: float = 5.0):
        """
        停止推流, 关闭 FFmpeg 子进程.

        Args:
            timeout: 等待子进程退出的秒数
        """
        if self._proc is None:
            return

        self._running = False
        proc = self._proc

        # 关闭 stdin 发送 EOF → FFmpeg 正常结束
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass

        # 等待退出
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg 未在 %ds 内退出, 强制终止", timeout)
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass

        # 读取残留 stderr
        stderr = self._try_read_stderr()
        if stderr:
            logger.info("FFmpeg stderr: %s", stderr.strip())

        elapsed = time.time() - self.start_time
        logger.info(
            "FFmpeg 推流已停止: %d 帧, %.1fs, 平均 %.1f FPS",
            self.frames_pushed, elapsed,
            self.frames_pushed / elapsed if elapsed > 0 else 0,
        )
        self._proc = None

    # ── 内部方法 ────────────────────────────────────

    def _build_command(self) -> list[str]:
        """构建 FFmpeg 命令行。"""
        return [
            self._ffmpeg_bin,
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self._width}x{self._height}",
            "-r", str(self.fps),
            "-i", "-",                           # 从 stdin 读取
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", self.preset,
            "-tune", self.tune,
            "-b:v", self.bitrate,
            "-f", "rtsp",
            self.dst_url,
        ]

    def _try_read_stderr(self) -> str:
        """尝试读取子进程的 stderr 内容。"""
        if self._proc is None or self._proc.stderr is None:
            return ""
        try:
            return self._proc.stderr.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()


# ─── 便捷工厂 ──────────────────────────────────────

def create_pusher(
    dst_url: str,
    width: int,
    height: int,
    fps: int = DEFAULT_FPS,
    **kwargs,
) -> Optional[FFmpegPusher]:
    """
    创建并启动推流器。

    Args:
        dst_url:  推流目标地址
        width:    帧宽度
        height:   帧高度
        fps:      帧率
        **kwargs: 传递给 FFmpegPusher 的额外参数

    Returns:
        FFmpegPusher 实例 (已启动), 失败返回 None
    """
    try:
        pusher = FFmpegPusher(dst_url=dst_url, fps=fps, **kwargs)
        if pusher.start(width, height):
            return pusher
        return None
    except Exception as exc:
        logger.error("创建推流器失败: %s", exc)
        return None
