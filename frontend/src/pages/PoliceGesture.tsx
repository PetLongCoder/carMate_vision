import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Progress,
  Segmented,
  Space,
  Tag,
  Upload,
  message,
} from 'antd';
import {
  ClockCircleOutlined,
  PauseCircleOutlined,
  UploadOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import { PageHeader } from '../components/common';
import type { PoliceGestureResult } from '../types';
import {
  createPoliceGesturePreview,
  recognizePoliceGestureFrame,
  resetPoliceGestureStream,
  streamPoliceGestureVideo,
} from '../api';
import { usePoliceGestureStore } from '../store/policeGestureStore';

const GESTURE_LABELS: Record<number, string> = {
  0: '无手势',
  1: '停止',
  2: '直行',
  3: '左转',
  4: '左转待转',
  5: '右转',
  6: '变道',
  7: '减速慢行',
  8: '靠边停车',
};

const GESTURE_COLORS: Record<number, string> = {
  0: '#8c8c8c',
  1: '#f5222d',
  2: '#1677ff',
  3: '#722ed1',
  4: '#eb2f96',
  5: '#fa8c16',
  6: '#52c41a',
  7: '#faad14',
  8: '#13c2c2',
};

type FrameResult = {
  frame: number;
  time: number;
  raw_time?: number;
  rawTime?: number;
  display_time?: number;
  gesture: string;
  gestureId: number;
  confidence: number;
  keypoints?: number[][];   // 14 [x,y] pairs from pose estimation
  policeOnly?: boolean;
  policeDetected?: boolean;
  policeCandidateDetected?: boolean;
  policeConfirmed?: boolean;
  policeConfirmStreak?: number;
  policeRequiredConfirmFrames?: number;
  policeConfidence?: number;
  policeClass?: string;
  policeBox?: number[];
  policeBoxNorm?: number[];
  policeCandidateConfidence?: number;
  policeCandidateClass?: string;
  policeNegativeConfidence?: number;
  policeNegativeClass?: string;
  policeRejectReason?: string | null;
};

type Segment = {
  start: number;
  end: number;
  gesture: string;
  gestureId: number;
};

type SegmentSummary = {
  gesture: string;
  gestureId: number;
  count: number;
  duration: number;
  firstStart: number;
};

type StreamRecord = PoliceGestureResult & {
  inference_ms?: number;
  proposedGesture?: string;
  proposedGestureId?: number;
  proposedConfidence?: number;
  rawGesture?: string;
  rawGestureId?: number;
  rawConfidence?: number;
  singleGesture?: string;
  singleGestureId?: number;
  singleConfidence?: number;
  policeOnly?: boolean;
  policeDetected?: boolean;
  policeCandidateDetected?: boolean;
  policeConfirmed?: boolean;
  policeConfirmStreak?: number;
  policeRequiredConfirmFrames?: number;
  policeConfidence?: number;
  policeClass?: string;
  policeBox?: number[];
  policeBoxNorm?: number[];
  policeCandidateConfidence?: number;
  policeCandidateClass?: string;
  policeNegativeConfidence?: number;
  policeNegativeClass?: string;
  policeRejectReason?: string | null;
  validPose?: boolean;
  poseQuality?: {
    score?: number;
    validUpperKeypoints?: number;
    validArmKeypoints?: number;
  };
  keypoints?: number[][];   // 14 [x,y] pairs from pose estimation
};

type PendingUpload = {
  file: File;
  uploadSeq: number;
  abortController: AbortController;
  policeOnly: boolean;
};

const STREAM_ID = 'web-camera-police-gesture';
const STREAM_INTERVAL_MS = 200;   // 200ms = 5fps, 保证每个手势能采到足够帧
const STREAM_FRAME_MAX_WIDTH = 768;
const STREAM_JPEG_QUALITY = 0.84;
const LIVE_LABEL_HOLD_SECONDS = 1.0;
type RecognitionMode = 'all' | 'police_only';
type PoliceDetectionOverlay = {
  policeCandidateDetected?: boolean;
  policeDetected?: boolean;
  policeConfirmed?: boolean;
  policeConfirmStreak?: number;
  policeRequiredConfirmFrames?: number;
  policeConfidence?: number;
  policeClass?: string;
  policeBoxNorm?: number[];
};

// 14 keypoints (0-indexed AI Challenger):
// 0=右肩, 1=右肘, 2=右腕, 3=左肩, 4=左肘, 5=左腕,
// 6=右髋, 7=右膝, 8=右踝, 9=左髋, 10=左膝, 11=左踝,
// 12=头顶, 13=颈部
const POLICE_BONES: [number, number][] = [
  [0, 1],   // 右大臂
  [1, 2],   // 右小臂
  [3, 4],   // 左大臂
  [4, 5],   // 左小臂
  [13, 0],  // 颈→右肩
  [13, 3],  // 颈→左肩
  [0, 6],   // 右侧躯干
  [3, 9],   // 左侧躯干
  [6, 7],   // 右大腿
  [7, 8],   // 右小腿
  [9, 10],  // 左大腿
  [10, 11], // 左小腿
  [12, 13], // 头→颈
];

const KEYPOINT_RADIUS = 5;
const BONE_LINE_WIDTH = 2.5;
const SKELETON_COLOR = '#00ff00';
const SKELETON_LOW_CONF_COLOR = 'rgba(255, 255, 255, 0.3)';

const getGestureLabel = (gestureId?: number, fallback?: string) => (
  gestureId === undefined ? '等待识别' : GESTURE_LABELS[gestureId] || fallback || '未知'
);

const getGestureColor = (gestureId?: number) => (
  gestureId === undefined ? '#8c8c8c' : GESTURE_COLORS[gestureId] || '#8c8c8c'
);

const formatSeconds = (seconds: number) => `${seconds.toFixed(1)}s`;

const getSkeletonFrameTime = (frame: FrameResult) => (
  Number(frame.rawTime ?? frame.raw_time ?? frame.time) || 0
);

const normalizeFrameResult = (frame: FrameResult): FrameResult => {
  const displayTime = Number(frame.time ?? frame.display_time ?? 0) || 0;
  const rawTime = Number(frame.rawTime ?? frame.raw_time ?? displayTime) || 0;
  return {
    ...frame,
    time: displayTime,
    raw_time: rawTime,
    rawTime,
    display_time: Number(frame.display_time ?? displayTime) || displayTime,
  };
};

// Cache last canvas dimensions to avoid expensive buffer reallocation
const _canvasDims = new WeakMap<HTMLCanvasElement, { w: number; h: number }>();

/**
 * Draw police gesture skeleton (14 keypoints + 13 bones) on a canvas overlay.
 * Normalized [0,1] coordinates are scaled to the container's display dimensions.
 * When validPose is false the skeleton is rendered at reduced opacity.
 *
 * Only resizes the canvas backing store when the container actually changes size,
 * which eliminates the frame-to-frame stutter caused by constant buffer reallocation.
 */
const drawSkeleton = (
  canvas: HTMLCanvasElement | null,
  containerEl: HTMLElement | null,
  keypoints: number[][] | undefined,
  isValid: boolean,
  mediaEl?: HTMLVideoElement | null,
  policeDetection?: PoliceDetectionOverlay,
) => {
  if (!canvas || !containerEl) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const rect = containerEl.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return;

  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(rect.width * dpr);
  const h = Math.round(rect.height * dpr);

  // Only resize the canvas backing store when dimensions actually change.
  // Setting canvas.width/height clears the buffer — we avoid this on every frame.
  const prev = _canvasDims.get(canvas);
  if (!prev || prev.w !== w || prev.h !== h) {
    canvas.width = w;
    canvas.height = h;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    _canvasDims.set(canvas, { w, h });
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);

  let mediaLeft = 0;
  let mediaTop = 0;
  let mediaWidth = rect.width;
  let mediaHeight = rect.height;
  if (mediaEl?.videoWidth && mediaEl.videoHeight) {
    const objectFit = window.getComputedStyle(mediaEl).objectFit;
    const scaleX = rect.width / mediaEl.videoWidth;
    const scaleY = rect.height / mediaEl.videoHeight;
    if (objectFit === 'cover' || objectFit === 'contain' || objectFit === 'scale-down') {
      const scale = objectFit === 'cover' ? Math.max(scaleX, scaleY) : Math.min(scaleX, scaleY);
      mediaWidth = mediaEl.videoWidth * scale;
      mediaHeight = mediaEl.videoHeight * scale;
      mediaLeft = (rect.width - mediaWidth) / 2;
      mediaTop = (rect.height - mediaHeight) / 2;
    }
  }

  const box = policeDetection?.policeBoxNorm;
  const hasCandidate = Boolean(policeDetection?.policeCandidateDetected ?? policeDetection?.policeDetected);
  const isConfirmed = Boolean(policeDetection?.policeConfirmed ?? policeDetection?.policeDetected);
  if (hasCandidate && box && box.length === 4) {
    const [x1, y1, x2, y2] = box;
    const left = mediaLeft + x1 * mediaWidth;
    const top = mediaTop + y1 * mediaHeight;
    const width = Math.max(1, (x2 - x1) * mediaWidth);
    const height = Math.max(1, (y2 - y1) * mediaHeight);
    const label = `${policeDetection.policeClass || 'traffic police'} ${Math.round((policeDetection.policeConfidence || 0) * 100)}%`;
    const color = isConfirmed ? '#13c2c2' : '#faad14';

    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.globalAlpha = 1;
    ctx.strokeRect(left, top, width, height);
    ctx.font = '600 14px Microsoft YaHei, sans-serif';
    const labelWidth = Math.min(ctx.measureText(label).width + 12, rect.width - 8);
    const labelTop = Math.max(0, top - 24);
    ctx.fillStyle = isConfirmed ? 'rgba(19, 194, 194, 0.92)' : 'rgba(250, 173, 20, 0.92)';
    ctx.fillRect(left, labelTop, labelWidth, 22);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, left + 6, labelTop + 16);
    ctx.restore();
  }

  if (!keypoints || keypoints.length < 14) return;

  // Scale normalized [0,1] coords to the actual rendered video area.
  const points = keypoints.map(([x, y]) => ({
    x: mediaLeft + x * mediaWidth,
    y: mediaTop + y * mediaHeight,
  }));

  const alpha = isValid ? 1.0 : 0.35;

  // Draw bones
  ctx.strokeStyle = isValid ? SKELETON_COLOR : SKELETON_LOW_CONF_COLOR;
  ctx.lineWidth = BONE_LINE_WIDTH;
  ctx.globalAlpha = alpha;
  for (const [a, b] of POLICE_BONES) {
    if (a >= points.length || b >= points.length) continue;
    const pa = points[a];
    const pb = points[b];
    // Skip if either endpoint is at origin (0,0) — likely invalid / not detected
    if ((pa.x < 0.01 && pa.y < 0.01) || (pb.x < 0.01 && pb.y < 0.01)) continue;
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.stroke();
  }

  // Draw keypoints
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    if (p.x < 0.01 && p.y < 0.01) continue;
    ctx.beginPath();
    ctx.arc(p.x, p.y, KEYPOINT_RADIUS, 0, 2 * Math.PI);
    ctx.fillStyle = isValid ? SKELETON_COLOR : SKELETON_LOW_CONF_COLOR;
    ctx.globalAlpha = alpha;
    ctx.fill();
  }
  ctx.globalAlpha = 1.0;
};

const PoliceGesture: React.FC = () => {
  // ---- 从 Zustand store 读取/写入识别结果 (切换页面不丢失) ----
  const storeResult = usePoliceGestureStore((s) => s.result);
  const storeTop5 = usePoliceGestureStore((s) => s.top5);
  const storeFrames = usePoliceGestureStore((s) => s.frames);
  const storeSegments = usePoliceGestureStore((s) => s.segments);
  const storeDuration = usePoliceGestureStore((s) => s.duration);
  const storeFps = usePoliceGestureStore((s) => s.fps);
  const storeSampleFps = usePoliceGestureStore((s) => s.sampleFps);
  const storeInferenceMs = usePoliceGestureStore((s) => s.inferenceMs);
  const storeVideoFileName = usePoliceGestureStore((s) => s.videoFileName);
  const storeStreamResult = usePoliceGestureStore((s) => s.streamResult);
  const storeStreamHistory = usePoliceGestureStore((s) => s.streamHistory);
  const storeSetVideoResult = usePoliceGestureStore((s) => s.setVideoResult);
  const storeSetVideoFileName = usePoliceGestureStore((s) => s.setVideoFileName);
  const storeSetStreamResult = usePoliceGestureStore((s) => s.setStreamResult);
  const storeAddStreamHistory = usePoliceGestureStore((s) => s.addStreamHistory);
  const storeClearVideoResult = usePoliceGestureStore((s) => s.clearVideoResult);
  const storeClearStream = usePoliceGestureStore((s) => s.clearStream);
  const setDuration = usePoliceGestureStore((s) => s.setDuration);
  const setFps = usePoliceGestureStore((s) => s.setFps);
  const setSampleFps = usePoliceGestureStore((s) => s.setSampleFps);
  const setFrames = usePoliceGestureStore((s) => s.setFrames);

  // 从 store 读取持久化的结果 (跨页面切换保留)
  const result = storeResult;
  const top5 = storeTop5;
  const frames = storeFrames;
  const segments = storeSegments;
  const duration = storeDuration;
  const fps = storeFps;
  const sampleFps = storeSampleFps;
  const inferenceMs = storeInferenceMs;
  const videoFileName = storeVideoFileName;
  const streamResult = storeStreamResult;
  const streamHistory = storeStreamHistory;

  // ---- 组件本地状态 (不需要跨页面保留) ----
  const [videoSrc, setVideoSrc] = React.useState<string | null>(null);
  const [videoError, setVideoError] = React.useState('');
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [playbackTime, setPlaybackTime] = React.useState(0);
  const [streaming, setStreaming] = React.useState(false);
  const [streamBusy, setStreamBusy] = React.useState(false);
  const [recognitionMode, setRecognitionMode] = React.useState<RecognitionMode>('all');
  const policeOnly = recognitionMode === 'police_only';

  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);       // 摄像头帧捕获（隐藏）
  const skeletonCanvasRef = useRef<HTMLCanvasElement>(null);     // 视频模式骨骼叠加
  const streamSkeletonCanvasRef = useRef<HTMLCanvasElement>(null); // 摄像头模式骨骼叠加
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | undefined>(undefined);
  const uploadSeqRef = useRef(0);
  const uploadAbortRef = useRef<AbortController | null>(null);
  const previewAbortRef = useRef<AbortController | null>(null);
  const videoUrlRef = useRef<string | null>(null);
  const pendingUploadRef = useRef<PendingUpload | null>(null);
  const analysisStartedRef = useRef(false);
  const analysisStartTimerRef = useRef<number | undefined>(undefined);
  const streamBusyRef = useRef(false);

  const segmentSummaries = useMemo<SegmentSummary[]>(() => {
    const summaries = new Map<number, SegmentSummary>();

    segments.forEach((seg) => {
      const durationSeconds = Math.max(seg.end - seg.start, 0);
      const current = summaries.get(seg.gestureId);

      if (current) {
        current.count += 1;
        current.duration += durationSeconds;
        current.firstStart = Math.min(current.firstStart, seg.start);
      } else {
        summaries.set(seg.gestureId, {
          gesture: seg.gesture,
          gestureId: seg.gestureId,
          count: 1,
          duration: durationSeconds,
          firstStart: seg.start,
        });
      }
    });

    return Array.from(summaries.values()).sort((a, b) => b.duration - a.duration);
  }, [segments]);

  const currentSegment = useMemo(() => (
    segments.find((seg) => playbackTime >= seg.start && playbackTime <= seg.end)
  ), [playbackTime, segments]);

  const currentFrame = useMemo(() => {
    if (!frames.length) return undefined;
    const pastFrames = frames.filter((frame) => frame.time <= playbackTime);
    const latestPastFrame = pastFrames[pastFrames.length - 1];
    if (latestPastFrame && playbackTime - latestPastFrame.time <= LIVE_LABEL_HOLD_SECONDS) {
      return latestPastFrame;
    }

    const futureFrame = frames.find((frame) => frame.time > playbackTime);
    if (futureFrame && futureFrame.time - playbackTime <= LIVE_LABEL_HOLD_SECONDS) {
      return futureFrame;
    }

    return latestPastFrame || futureFrame || frames[frames.length - 1];
  }, [frames, playbackTime]);

  // Skeleton uses the nearest PAST frame only — never a future frame.
  const SKELETON_HOLD_SECONDS = 0.8;

  // requestVideoFrameCallback fires AFTER each video frame is presented to the
  // compositor, ensuring the skeleton canvas is drawn in perfect sync with the
  // video image. Falls back to timeupdate + rAF when rvfc is not available.
  useEffect(() => {
    if (!videoSrc) return;
    const video = videoRef.current;
    const canvas = skeletonCanvasRef.current;
    if (!video || !canvas) return;
    const containerEl = canvas.parentElement;

    const frameApi = video as unknown as {
      requestVideoFrameCallback?: (cb: (now: number, metadata: { presentationTime: number; mediaTime?: number }) => void) => number;
      cancelVideoFrameCallback?: (id: number) => void;
    };
    const requestVideoFrameCallback = frameApi.requestVideoFrameCallback?.bind(video);
    const cancelVideoFrameCallback = frameApi.cancelVideoFrameCallback?.bind(video);

    let rvfcId = 0;
    let rafId = 0;
    let running = true;

    const onFrame = (mediaTime?: number) => {
      if (!running) return;
      const pt = Math.max(0, mediaTime ?? video.currentTime);
      const past = frames.filter((f) => getSkeletonFrameTime(f) <= pt && (f.keypoints?.length || f.policeDetected));
      const match = past[past.length - 1];
      if (match && pt - getSkeletonFrameTime(match) <= SKELETON_HOLD_SECONDS) {
        drawSkeleton(canvas, containerEl, match.keypoints, true, video, match);
      } else {
        drawSkeleton(canvas, containerEl, undefined, true, video);
      }
    };

    if (requestVideoFrameCallback && cancelVideoFrameCallback) {
      const loop = (_now: number, metadata: { mediaTime?: number }) => {
        if (!running) return;
        onFrame(metadata.mediaTime);
        rvfcId = requestVideoFrameCallback(loop);
      };
      rvfcId = requestVideoFrameCallback(loop);
    } else {
      // Fallback: use rAF, which fires just before compositor presents —
      // this is still closer to the actual video frame than timeupdate.
      const loop = () => {
        if (!running) return;
        onFrame();
        rafId = requestAnimationFrame(loop);
      };
      rafId = requestAnimationFrame(loop);
    }

    return () => {
      running = false;
      if (rvfcId && cancelVideoFrameCallback) cancelVideoFrameCallback(rvfcId);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [videoSrc, frames]);

  // Resize skeleton canvas when video container size changes
  useEffect(() => {
    const canvas = skeletonCanvasRef.current;
    if (!canvas) return;
    const containerEl = canvas.parentElement;
    if (!containerEl) return;
    const observer = new ResizeObserver(() => {
      // Reset cached dims so drawSkeleton picks up the new size
      _canvasDims.delete(canvas);
    });
    observer.observe(containerEl);
    return () => observer.disconnect();
  }, []);

  const overlayGestureId = currentSegment?.gestureId ?? currentFrame?.gestureId;
  const overlayLabel = overlayGestureId !== undefined
    ? getGestureLabel(overlayGestureId, currentSegment?.gesture || currentFrame?.gesture)
    : loading
      ? '正在分析'
      : '等待标注';
  const overlayColor = getGestureColor(overlayGestureId);
  const currentConfidence = currentFrame?.confidence;
  const primarySummary = segmentSummaries[0];

  const startStreamAnalysis = useCallback(async (pending: PendingUpload) => {
    const { file, uploadSeq, abortController, policeOnly: pendingPoliceOnly } = pending;
    if (analysisStartedRef.current || uploadSeqRef.current !== uploadSeq) return;

    analysisStartedRef.current = true;
    message.success('后端开始边分析边返回结果');

    try {
      await streamPoliceGestureVideo(
        file,
        ({ event, data }) => {
          if (uploadSeqRef.current !== uploadSeq) return;

          if (event === 'meta') {
            setDuration(Number(data.video_duration) || videoRef.current?.duration || 0);
            setFps(Number(data.video_fps) || 0);
            setSampleFps(Number(data.sample_fps) || 0);
            return;
          }

          if (event === 'frame') {
            const frame = data as FrameResult & { progress?: number; keypoints?: number[][] };
            setFrames((items) => [...items, normalizeFrameResult({
              frame: frame.frame,
              time: frame.time,
              raw_time: frame.raw_time,
              rawTime: frame.rawTime,
              display_time: frame.display_time,
              gesture: frame.gesture,
              gestureId: frame.gestureId,
              confidence: frame.confidence,
              keypoints: frame.keypoints,
              policeOnly: frame.policeOnly,
              policeDetected: frame.policeDetected,
              policeCandidateDetected: frame.policeCandidateDetected,
              policeConfirmed: frame.policeConfirmed,
              policeConfirmStreak: frame.policeConfirmStreak,
              policeRequiredConfirmFrames: frame.policeRequiredConfirmFrames,
              policeConfidence: frame.policeConfidence,
              policeClass: frame.policeClass,
              policeBox: frame.policeBox,
              policeBoxNorm: frame.policeBoxNorm,
            })]);
            setProgress(Math.max(1, Math.min(99, Number(frame.progress) || 1)));
            return;
          }

          if (event === 'done') {
            const doneData = data as unknown as PoliceGestureResult & {
              top5?: Array<{ gesture: string; gestureId: number; confidence: number }>;
              inference_ms?: number;
              frames?: FrameResult[];
              segments?: Segment[];
              video_duration?: number;
              video_fps?: number;
              sample_fps?: number;
            };
            setProgress(100);
            // 持久化到 Zustand store (切换页面不丢失)
            storeSetVideoResult({
              result: {
                gesture: doneData.gesture,
                gestureId: doneData.gestureId,
                confidence: doneData.confidence,
                timestamp: doneData.timestamp,
              },
              top5: doneData.top5 || [],
              frames: (doneData.frames || []).map(normalizeFrameResult),
              segments: doneData.segments || [],
              duration: doneData.video_duration || videoRef.current?.duration || 0,
              fps: doneData.video_fps || 0,
              sampleFps: doneData.sample_fps || 0,
              inferenceMs: doneData.inference_ms || 0,
            });
            message.success(`识别完成：${getGestureLabel(doneData.gestureId, doneData.gesture)}`);
            return;
          }

          if (event === 'error') {
            throw new Error((data as { message?: string }).message || '流式识别失败');
          }
        },
        abortController.signal,
        pendingPoliceOnly,
      );
    } catch (error) {
      if (abortController.signal.aborted) return;
      if (uploadSeqRef.current !== uploadSeq) return;
      setProgress(0);
      console.error('police gesture upload failed:', error);
      message.error('识别失败，请确认后端服务已启动');
    } finally {
      if (uploadSeqRef.current === uploadSeq) {
        setLoading(false);
      }
    }
  }, []);

  const startPendingAnalysis = useCallback(() => {
    if (!pendingUploadRef.current) return;
    void startStreamAnalysis(pendingUploadRef.current);
  }, [startStreamAnalysis]);

  const replaceVideoSource = useCallback((url: string) => {
    if (videoUrlRef.current) {
      URL.revokeObjectURL(videoUrlRef.current);
    }
    videoUrlRef.current = url;
    setVideoSrc(url);
    setPlaybackTime(0);
  }, []);

  const createPreviewVideo = useCallback(async (file: File, uploadSeq: number) => {
    const abortController = new AbortController();
    previewAbortRef.current = abortController;
    setPreviewLoading(true);

    try {
      const previewBlob = await createPoliceGesturePreview(file, abortController.signal);
      if (uploadSeqRef.current !== uploadSeq || abortController.signal.aborted) return;
      replaceVideoSource(URL.createObjectURL(previewBlob));
      setVideoError('');
      message.success('已生成浏览器兼容预览视频');
    } catch (error) {
      if (abortController.signal.aborted || uploadSeqRef.current !== uploadSeq) return;
      console.warn('preview transcode failed:', error);
      setVideoError('预览转码不可用，已尝试播放原视频；如果仍无法播放，请确认后端已安装 imageio-ffmpeg 或系统 FFmpeg。');
    } finally {
      if (uploadSeqRef.current === uploadSeq) {
        setPreviewLoading(false);
      }
    }
  }, [replaceVideoSource]);

  const handleUpload = (file: File) => {
    const uploadSeq = uploadSeqRef.current + 1;
    uploadSeqRef.current = uploadSeq;
    uploadAbortRef.current?.abort();
    previewAbortRef.current?.abort();
    if (analysisStartTimerRef.current) {
      window.clearTimeout(analysisStartTimerRef.current);
      analysisStartTimerRef.current = undefined;
    }

    const abortController = new AbortController();
    uploadAbortRef.current = abortController;
    pendingUploadRef.current = { file, uploadSeq, abortController, policeOnly };
    analysisStartedRef.current = false;

    setLoading(true);
    setProgress(0);
    storeClearVideoResult();
    setPlaybackTime(0);
    storeSetVideoFileName(file.name);
    setVideoError('');
    setPreviewLoading(false);

    const objectUrl = URL.createObjectURL(file);
    replaceVideoSource(objectUrl);
    message.success('视频已载入，正在生成兼容预览并进行流式分析');

    void createPreviewVideo(file, uploadSeq);

    analysisStartTimerRef.current = window.setTimeout(() => {
      analysisStartTimerRef.current = undefined;
      startPendingAnalysis();
    }, 1200);

    return false;
  };

  const seekTo = (seconds: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      setPlaybackTime(seconds);
      void videoRef.current.play();
    }
  };

  const stopCamera = useCallback(async () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = undefined;
    }
    streamBusyRef.current = false;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (cameraRef.current) {
      cameraRef.current.srcObject = null;
    }
    setStreaming(false);
    setStreamBusy(false);
    // Clear skeleton overlay
    const ctx = streamSkeletonCanvasRef.current?.getContext('2d');
    if (ctx && streamSkeletonCanvasRef.current) {
      ctx.clearRect(0, 0, streamSkeletonCanvasRef.current.width, streamSkeletonCanvasRef.current.height);
    }
    await resetPoliceGestureStream(STREAM_ID).catch(() => undefined);
  }, []);

  const captureAndRecognize = useCallback(async () => {
    if (!cameraRef.current || !canvasRef.current || streamBusyRef.current) return;
    const video = cameraRef.current;
    if (!video.videoWidth || !video.videoHeight) return;

    streamBusyRef.current = true;
    setStreamBusy(true);
    const canvas = canvasRef.current;
    const scale = Math.min(1, STREAM_FRAME_MAX_WIDTH / video.videoWidth);
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      streamBusyRef.current = false;
      setStreamBusy(false);
      return;
    }

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(async (blob) => {
      if (!blob) {
        streamBusyRef.current = false;
        setStreamBusy(false);
        return;
      }

      try {
        const response = await recognizePoliceGestureFrame(blob, STREAM_ID, policeOnly);
        const data = ((response.data as any).data || response.data) as StreamRecord & { keypoints?: number[][] };
        storeSetStreamResult(data);
        storeAddStreamHistory(data);

        // Draw skeleton overlay on webcam video
        const containerEl = streamSkeletonCanvasRef.current?.parentElement;
        if (containerEl) {
          drawSkeleton(streamSkeletonCanvasRef.current, containerEl, data.keypoints, data.validPose ?? true, video, data);
        }
      } catch (error) {
        console.error('stream frame failed:', error);
        message.warning('实时帧识别失败，请检查后端服务');
      } finally {
        streamBusyRef.current = false;
        setStreamBusy(false);
      }
    }, 'image/jpeg', STREAM_JPEG_QUALITY);
  }, [policeOnly, storeAddStreamHistory, storeSetStreamResult]);

  const startCamera = async () => {
    try {
      await resetPoliceGestureStream(STREAM_ID);
      const media = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 960 },
          height: { ideal: 720 },
          facingMode: 'environment',
        },
        audio: false,
      });
      streamRef.current = media;
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = undefined;
      }
      streamBusyRef.current = false;
      if (cameraRef.current) {
        cameraRef.current.srcObject = media;
        await cameraRef.current.play();
      }
      storeClearStream();
      setStreaming(true);
      timerRef.current = window.setInterval(captureAndRecognize, STREAM_INTERVAL_MS);
      window.setTimeout(captureAndRecognize, 300);
    } catch (error) {
      console.error('camera start failed:', error);
      message.error('无法打开摄像头，请检查浏览器权限');
    }
  };

  useEffect(() => {
    return () => {
      uploadSeqRef.current += 1;
      uploadAbortRef.current?.abort();
      previewAbortRef.current?.abort();
      if (analysisStartTimerRef.current) window.clearTimeout(analysisStartTimerRef.current);
      if (timerRef.current) window.clearInterval(timerRef.current);
      streamBusyRef.current = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (videoUrlRef.current) URL.revokeObjectURL(videoUrlRef.current);
    };
  }, []);

  const streamLabel = getGestureLabel(streamResult?.gestureId, streamResult?.gesture);
  const streamColor = getGestureColor(streamResult?.gestureId);
  const policeGateConfirmed = Boolean(streamResult?.policeConfirmed ?? streamResult?.policeDetected);
  const policeGateCandidate = Boolean(streamResult?.policeCandidateDetected ?? streamResult?.policeDetected);
  const streamDisplayLabel = policeOnly
    ? (policeGateConfirmed
        ? streamLabel
        : policeGateCandidate
          ? `交警候选 ${streamResult?.policeClass || 'traffic police'}`
          : '未检测到交警')
    : streamLabel;
  const streamDisplayColor = policeOnly
    ? (policeGateConfirmed ? streamColor : '#faad14')
    : streamColor;

  return (
    <div>
      <PageHeader
        title="交警手势识别"
        subtitle="上传视频后立即播放预览，后台基于连续帧时序分析并按播放时间标注动作"
        extra={
          <Space>
            {streaming ? (
              <Button icon={<PauseCircleOutlined />} onClick={stopCamera}>
                停止摄像头
              </Button>
            ) : (
              <Button icon={<VideoCameraOutlined />} type="primary" onClick={startCamera}>
                实时摄像头
              </Button>
            )}
          </Space>
        }
      />

      <Card style={{ marginBottom: 16 }}>
        <Space align="center" wrap>
          <span style={{ color: '#595959' }}>识别模式</span>
          <Segmented
            value={recognitionMode}
            disabled={loading || streaming}
            onChange={(value) => setRecognitionMode(value as RecognitionMode)}
            options={[
              { label: '全部人体', value: 'all' },
              { label: '仅交警', value: 'police_only' },
            ]}
          />
          {policeOnly && (
            <Tag color="blue">YOLO-World</Tag>
          )}
        </Space>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 1.3fr) minmax(320px, 0.7fr)', gap: 16 }}>
        <Card
          title="上传视频预览"
          extra={videoSrc && <Tag color={previewLoading ? 'processing' : loading ? 'processing' : segments.length ? 'green' : 'default'}>{previewLoading ? '生成预览' : loading ? '分析中' : segments.length ? `${segments.length} 段动作` : '待分析'}</Tag>}
        >
          {videoSrc ? (
            <div style={{ position: 'relative', background: '#000', borderRadius: 8, overflow: 'hidden' }}>
              <video
                key={videoSrc}
                ref={videoRef}
                src={videoSrc}
                controls
                muted
                playsInline
                preload="auto"
                onLoadedMetadata={(event) => {
                  setDuration(event.currentTarget.duration || duration);
                  void event.currentTarget.play().catch(() => undefined);
                  startPendingAnalysis();
                }}
                onCanPlay={(event) => {
                  setVideoError('');
                  void event.currentTarget.play().catch(() => undefined);
                  startPendingAnalysis();
                }}
                onError={() => {
                  setVideoError('当前视频可以继续后端分析，但浏览器无法播放这个视频编码。建议转为 H.264 编码的 MP4 后再上传预览。');
                  startPendingAnalysis();
                }}
                onTimeUpdate={(event) => setPlaybackTime(event.currentTarget.currentTime)}
                style={{ width: '100%', maxHeight: 430, display: 'block', background: '#000' }}
              />
              <canvas
                ref={skeletonCanvasRef}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  left: 16,
                  top: 16,
                  padding: '8px 14px',
                  borderRadius: 6,
                  background: overlayColor,
                  color: '#fff',
                  fontSize: 20,
                  fontWeight: 700,
                  boxShadow: '0 8px 20px rgba(0,0,0,0.28)',
                }}
              >
                {overlayLabel}
              </div>
              {currentSegment && (
                <div
                  style={{
                    position: 'absolute',
                    left: 16,
                    bottom: 16,
                    padding: '6px 10px',
                    borderRadius: 6,
                    background: 'rgba(0,0,0,0.68)',
                    color: '#fff',
                  }}
                >
                  {currentSegment.start.toFixed(1)}s - {currentSegment.end.toFixed(1)}s
                </div>
              )}
            </div>
          ) : (
            <Empty description="选择视频后会立即播放预览，识别完成后按时间标注动作" />
          )}
          {videoError && (
            <Alert
              type="warning"
              showIcon
              message={videoError}
              style={{ marginTop: 12 }}
            />
          )}
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <Upload accept="video/*" showUploadList={false} beforeUpload={handleUpload} disabled={loading}>
              <Button icon={<UploadOutlined />} size="large" loading={loading}>
                选择视频文件
              </Button>
            </Upload>
            <div style={{ marginTop: 8, color: '#8c8c8c' }}>{videoFileName || '支持 MP4、AVI、MOV、WebM、MKV'}</div>
          </div>
          {loading && (
            <div style={{ margin: '18px auto 0', maxWidth: 420 }}>
              <Progress percent={progress} status="active" strokeColor="#1677ff" />
              <span style={{ color: '#8c8c8c' }}>
                {previewLoading ? '正在生成浏览器兼容 MP4 预览，同时进行 LSTM 时序分析' : '正在连续提取关键点并进行 LSTM 时序分类，视频可先播放预览'}
              </span>
            </div>
          )}
        </Card>

        <Card
          title="视频识别结果"
          extra={segments.length > 0 && <Tag color="blue">{segments.length} 段</Tag>}
        >
          {result || frames.length > 0 || segments.length > 0 ? (
            <div>
              <div
                style={{
                  border: `1px solid ${overlayColor}`,
                  borderRadius: 8,
                  padding: 12,
                  background: `${overlayColor}12`,
                  marginBottom: 12,
                }}
              >
                <div style={{ color: '#8c8c8c', fontSize: 13, marginBottom: 6 }}>
                  当前播放位置
                </div>
                <Space align="center" wrap>
                  <Tag color={overlayColor} style={{ fontSize: 16, padding: '4px 12px' }}>
                    {overlayLabel}
                  </Tag>
                  <span style={{ color: '#595959' }}>
                    {formatSeconds(playbackTime)}
                    {currentSegment ? ` / ${formatSeconds(currentSegment.start)} - ${formatSeconds(currentSegment.end)}` : ''}
                  </span>
                  {currentConfidence !== undefined && (
                    <span style={{ color: '#8c8c8c' }}>
                      置信度 {(currentConfidence * 100).toFixed(0)}%
                    </span>
                  )}
                </Space>
              </div>

              <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
                <Descriptions.Item label="识别到的动作段">{segments.length || '-'}</Descriptions.Item>
                <Descriptions.Item label="主要动作">
                  {primarySummary ? (
                    <Tag color={getGestureColor(primarySummary.gestureId)}>
                      {getGestureLabel(primarySummary.gestureId, primarySummary.gesture)}
                      {' '}
                      {formatSeconds(primarySummary.duration)}
                    </Tag>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="推理耗时">{inferenceMs ? `${inferenceMs.toFixed(0)} ms` : '-'}</Descriptions.Item>
                <Descriptions.Item label="分析帧数">{frames.length ? `${frames.length} 帧` : '-'}</Descriptions.Item>
                <Descriptions.Item label="视频帧率">{fps || '-'} fps</Descriptions.Item>
                <Descriptions.Item label="采样帧率">{sampleFps || '-'} fps</Descriptions.Item>
              </Descriptions>

              {segmentSummaries.length > 0 ? (
                <div>
                  <div style={{ color: '#8c8c8c', fontSize: 13, marginBottom: 8 }}>
                    动作分布
                  </div>
                  <Space direction="vertical" style={{ width: '100%' }} size={8}>
                    {segmentSummaries.map((item) => {
                      const percent = duration ? Math.round((item.duration / duration) * 100) : 0;
                      return (
                        <button
                          key={item.gestureId}
                          type="button"
                          onClick={() => seekTo(item.firstStart)}
                          style={{
                            width: '100%',
                            border: '1px solid #f0f0f0',
                            borderRadius: 8,
                            background: '#fff',
                            padding: '8px 10px',
                            cursor: 'pointer',
                            textAlign: 'left',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
                            <span>
                              <Tag color={getGestureColor(item.gestureId)} style={{ marginInlineEnd: 8 }}>
                                {getGestureLabel(item.gestureId, item.gesture)}
                              </Tag>
                              <span style={{ color: '#8c8c8c' }}>{item.count} 段</span>
                            </span>
                            <span style={{ color: '#595959' }}>{formatSeconds(item.duration)}</span>
                          </div>
                          <Progress
                            percent={percent}
                            size="small"
                            showInfo={false}
                            strokeColor={getGestureColor(item.gestureId)}
                          />
                        </button>
                      );
                    })}
                  </Space>
                </div>
              ) : top5.length > 0 ? (
                <div>
                  <div style={{ color: '#8c8c8c', fontSize: 13, marginBottom: 8 }}>
                    全片候选结果
                  </div>
                  <Space wrap>
                    {top5.map((item) => (
                      <Tag key={item.gestureId} color={getGestureColor(item.gestureId)}>
                        {getGestureLabel(item.gestureId, item.gesture)} {(item.confidence * 100).toFixed(0)}%
                      </Tag>
                    ))}
                  </Space>
                </div>
              ) : null}
            </div>
          ) : (
            <Empty description={loading ? '等待后端返回时序识别结果' : '上传视频后显示识别结果'} />
          )}
        </Card>
      </div>

      {segments.length > 0 && (
        <Card
          title="视频动作时间线"
          style={{ marginTop: 16 }}
          extra={<span style={{ color: '#8c8c8c' }}><ClockCircleOutlined /> 点击动作段跳转并播放</span>}
        >
          <div style={{ position: 'relative', height: 56, background: '#f5f5f5', borderRadius: 8, overflow: 'hidden' }}>
            {segments.map((seg, index) => {
              const left = duration ? (seg.start / duration) * 100 : 0;
              const width = duration ? Math.max(((seg.end - seg.start) / duration) * 100, 1) : 1;
              return (
                <button
                  key={`${seg.start}-${index}`}
                  type="button"
                  onClick={() => seekTo(seg.start)}
                  title={`${seg.start.toFixed(1)}s - ${seg.end.toFixed(1)}s: ${getGestureLabel(seg.gestureId, seg.gesture)}`}
                  style={{
                    position: 'absolute',
                    left: `${left}%`,
                    width: `${width}%`,
                    height: '100%',
                    border: 0,
                    borderRight: '2px solid #fff',
                    background: getGestureColor(seg.gestureId),
                    color: '#fff',
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  {width > 8 ? getGestureLabel(seg.gestureId, seg.gesture) : ''}
                </button>
              );
            })}
          </div>
          <Space wrap style={{ marginTop: 16 }}>
            {segments.map((seg, index) => (
              <Tag
                key={`${seg.end}-${index}`}
                color={getGestureColor(seg.gestureId)}
                style={{ cursor: 'pointer', padding: '4px 10px' }}
                onClick={() => seekTo(seg.start)}
              >
                {getGestureLabel(seg.gestureId, seg.gesture)}: {seg.start.toFixed(1)}s - {seg.end.toFixed(1)}s
              </Tag>
            ))}
          </Space>
        </Card>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 1.3fr) minmax(320px, 0.7fr)', gap: 16, marginTop: 16 }}>
        <Card
          title="实时视频流"
          extra={<Tag color={streaming ? 'green' : 'default'}>{streaming ? (streamBusy ? '分析中' : '运行中') : '未开启'}</Tag>}
        >
          <div style={{ position: 'relative', background: '#000', borderRadius: 8, overflow: 'hidden', minHeight: 280 }}>
            <video
              ref={cameraRef}
              muted
              playsInline
              style={{ width: '100%', height: 360, objectFit: 'cover', display: 'block' }}
            />
            <canvas
              ref={streamSkeletonCanvasRef}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: 16,
                top: 16,
                padding: '8px 14px',
                borderRadius: 6,
                background: streamDisplayColor,
                color: '#fff',
                fontSize: 20,
                fontWeight: 700,
              }}
            >
              {streamDisplayLabel}
            </div>
            {streamResult && (
              <div style={{ position: 'absolute', right: 16, bottom: 16, padding: '6px 10px', borderRadius: 6, background: 'rgba(0,0,0,0.65)', color: '#fff' }}>
                置信度 {(streamResult.confidence * 100).toFixed(1)}%
              </div>
            )}
          </div>
          <canvas ref={canvasRef} style={{ display: 'none' }} />
        </Card>

        <Card title="实时识别结果">
          {streamResult ? (
            <div style={{ textAlign: 'center' }}>
              <Tag color={streamDisplayColor} style={{ fontSize: 22, padding: '6px 20px', marginBottom: 16 }}>
                {streamDisplayLabel}
              </Tag>
              <Progress
                type="circle"
                percent={Math.round(streamResult.confidence * 100)}
                size={96}
                strokeColor={streamDisplayColor}
              />
              <Descriptions size="small" column={1} style={{ marginTop: 16, textAlign: 'left' }}>
                <Descriptions.Item label="推理耗时">{streamResult.inference_ms?.toFixed(0) || 0} ms</Descriptions.Item>
                <Descriptions.Item label="姿态质量">
                  {streamResult.poseQuality
                    ? `${((streamResult.poseQuality.score || 0) * 100).toFixed(0)}%`
                    : '-'}
                  {streamResult.validPose === false ? '（未稳定捕获人体）' : ''}
                </Descriptions.Item>
                {policeOnly && (
                  <Descriptions.Item label="YOLO-World">
                    {streamResult.policeDetected
                      ? `${streamResult.policeClass || 'traffic police'} ${((streamResult.policeConfidence || 0) * 100).toFixed(0)}%`
                      : (streamResult.policeDetectionError
                          ? `error: ${streamResult.policeDetectionError}`
                          : `${streamResult.policeCandidateDetected ? 'candidate, waiting confirm' : (streamResult.policeRejectReason || 'not traffic police')}${streamResult.policeNegativeClass ? ` (${streamResult.policeNegativeClass} ${((streamResult.policeNegativeConfidence || 0) * 100).toFixed(0)}%)` : ''}`)}
                    {streamResult.policeCandidateDetected && !streamResult.policeDetected
                      ? ` ${streamResult.policeConfirmStreak || 0}/${streamResult.policeRequiredConfirmFrames || 0}`
                      : ''}
                  </Descriptions.Item>
                )}
                <Descriptions.Item label="Raw">
                  {getGestureLabel(streamResult.rawGestureId, streamResult.rawGesture)}
                  {streamResult.rawConfidence !== undefined ? ` ${(streamResult.rawConfidence * 100).toFixed(0)}%` : ''}
                </Descriptions.Item>
                <Descriptions.Item label="Proposed">
                  {getGestureLabel(streamResult.proposedGestureId, streamResult.proposedGesture)}
                  {streamResult.proposedConfidence !== undefined ? ` ${(streamResult.proposedConfidence * 100).toFixed(0)}%` : ''}
                </Descriptions.Item>
                <Descriptions.Item label="Single">
                  {getGestureLabel(streamResult.singleGestureId, streamResult.singleGesture)}
                  {streamResult.singleConfidence !== undefined ? ` ${(streamResult.singleConfidence * 100).toFixed(0)}%` : ''}
                </Descriptions.Item>
                <Descriptions.Item label="输入类型">连续摄像头帧</Descriptions.Item>
                <Descriptions.Item label="时序状态">LSTM 状态保持</Descriptions.Item>
              </Descriptions>
            </div>
          ) : (
            <Empty description="打开摄像头后显示实时手势" />
          )}
        </Card>
      </div>

      {streamHistory.length > 0 && (
        <Card title="实时识别记录" style={{ marginTop: 16 }}>
          <Space wrap>
            {streamHistory.map((item, index) => (
              <Tag key={`${item.timestamp}-${index}`} color={getGestureColor(item.gestureId)}>
                {getGestureLabel(item.gestureId, item.gesture)} {(item.confidence * 100).toFixed(0)}%
              </Tag>
            ))}
          </Space>
        </Card>
      )}
    </div>
  );
};

export default PoliceGesture;
