import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Card, Upload, Button, Space, Tag, Table, message, Tabs, Input,
  Progress, Badge, Typography, Alert, Spin,
} from 'antd';
import {
  CameraOutlined, InboxOutlined, PlayCircleOutlined,
  StopOutlined, LinkOutlined, VideoCameraOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { PageHeader, Empty } from '../components/common';
import {
  uploadPlateImage, uploadTrackVideo, startStreamTracking,
  stopStreamTracking,
} from '../api';
import type {
  PlateResult, TrackedPlateResult, TrackedPlateSummary,
  WsPlateMessage, FrameDetection, SessionStatusMsg,
  TrackingSummary,
} from '../types';

const { Dragger } = Upload;
const { Text } = Typography;

// ═══════════════════════════════════════════════════════════
//  常量
// ═══════════════════════════════════════════════════════════

const IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.bmp', '.webp'];
const VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'];

const VEHICLE_TYPE_MAP: Record<string, { label: string; color: string; icon: string }> = {
  car: { label: '轿车', color: 'blue', icon: '🚗' },
  bus: { label: '客车', color: 'purple', icon: '🚌' },
  truck: { label: '卡车', color: 'orange', icon: '🚛' },
  motorcycle: { label: '摩托车', color: 'cyan', icon: '🏍️' },
  unknown: { label: '未知', color: 'default', icon: '🚘' },
};

const PLATE_COLOR_MAP: Record<string, { label: string; color: string }> = {
  blue: { label: '蓝牌', color: 'blue' },
  green: { label: '绿牌', color: 'green' },
  yellow: { label: '黄牌', color: 'orange' },
  white: { label: '白牌', color: 'default' },
  black: { label: '黑牌', color: 'default' },
};

function isVideoFile(file: File): boolean {
  const ext = '.' + file.name.split('.').pop()?.toLowerCase();
  if (VIDEO_EXTENSIONS.includes(ext)) return true;
  if (IMAGE_EXTENSIONS.includes(ext)) return false;
  return file.type.startsWith('video/');
}

// ═══════════════════════════════════════════════════════════
//  画布绘制工具
// ═══════════════════════════════════════════════════════════

function getColorForPlate(plateColor: string): string {
  const map: Record<string, string> = {
    blue: '#1677ff',
    green: '#52c41a',
    yellow: '#faad14',
    white: '#d9d9d9',
    black: '#262626',
  };
  return map[plateColor] || '#ff7a00';
}

function drawDetectionsOnCanvas(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
  detections: TrackedPlateResult[],
) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = video.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  ctx.scale(dpr, dpr);

  const scaleX = rect.width / video.videoWidth;
  const scaleY = rect.height / video.videoHeight;

  ctx.clearRect(0, 0, rect.width, rect.height);

  for (const d of detections) {
    const x = d.bbox.x * scaleX;
    const y = d.bbox.y * scaleY;
    const w = d.bbox.width * scaleX;
    const h = d.bbox.height * scaleY;
    const color = getColorForPlate(d.color);

    // 边框
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);

    // 车牌号标签 (框上方)
    const label = `${d.plateNo}`;
    ctx.font = 'bold 14px -apple-system, sans-serif';
    const tw = ctx.measureText(label).width;

    const labelY = y > 30 ? y - 8 : y + h + 8;
    const bgH = 24;

    // 标签背景
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(x, labelY - bgH, tw + 16, bgH, 4);
    ctx.fill();

    // 标签文字
    ctx.fillStyle = '#fff';
    ctx.fillText(label, x + 8, labelY - 7);

    // 第二行: ID + 颜色 + 车型 + 置信度
    const vt = VEHICLE_TYPE_MAP[d.vehicleType];
    const info = `#${d.trackId} · ${d.color} · ${vt?.icon||''} ${vt?.label||d.vehicleType} · ${(d.confidence * 100).toFixed(0)}%`;
    ctx.font = '11px -apple-system, sans-serif';
    const infoY = y > 30 ? y - 36 : y + h + 36;
    ctx.fillStyle = color;
    ctx.fillText(info, x, infoY);
  }
}

/**
 * 在有序帧数组中二分查找最接近 targetTime 的帧
 * 始终返回最近匹配（不设 maxDiff 限制），无数据返回 null
 */
function findNearestFrame(
  frames: { timestamp: number; detections: TrackedPlateResult[] }[],
  targetTime: number,
): { detections: TrackedPlateResult[]; timestamp: number } | null {
  if (frames.length === 0) return null;
  if (targetTime <= frames[0].timestamp) return frames[0];
  if (targetTime >= frames[frames.length - 1].timestamp) return frames[frames.length - 1];

  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].timestamp < targetTime) {
      lo = mid;
    } else {
      hi = mid;
    }
  }

  const loDiff = Math.abs(frames[lo].timestamp - targetTime);
  const hiDiff = Math.abs(frames[hi].timestamp - targetTime);
  return loDiff <= hiDiff ? frames[lo] : frames[hi];
}

// ═══════════════════════════════════════════════════════════
//  主组件
// ═══════════════════════════════════════════════════════════

type PageMode = 'upload' | 'track' | 'stream';

const PlateRecognition: React.FC = () => {
  // ── 模式 ──
  const [mode, setMode] = useState<PageMode>('upload');

  // ── Upload 模式状态 ──
  const [results, setResults] = useState<PlateResult[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isVideo, setIsVideo] = useState(false);
  const [loading, setLoading] = useState(false);
  const [imageScale, setImageScale] = useState({ x: 1, y: 1 });

  // ── Track 模式状态 ──
  const [trackSessionId, setTrackSessionId] = useState<string | null>(null);
  const [trackLoading, setTrackLoading] = useState(false);
  const [wsStatus, setWsStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [trackProgress, setTrackProgress] = useState(0);
  const [trackStatusMsg, setTrackStatusMsg] = useState('');
  const [trackedPlates, setTrackedPlates] = useState<TrackedPlateSummary[]>([]);
  const [trackTotalFrames, setTrackTotalFrames] = useState(0);
  const [trackProcessedFrames, setTrackProcessedFrames] = useState(0);
  const [trackDuration, setTrackDuration] = useState(0);
  const [detectionLog, setDetectionLog] = useState<{ time: number; count: number; plateNos: string[] }[]>([]);

  // 按真实时间戳索引的检测结果 (WebSocket 推送时由实际 timestamp 建立)
  const [timeIndexedDetections, setTimeIndexedDetections] = useState<Map<number, TrackedPlateResult[]>>(new Map());
  // 有序帧数组 (按 timestamp 升序), 用于二分查找
  const detectionFramesRef = useRef<{ timestamp: number; detections: TrackedPlateResult[] }[]>([]);

  // 当前视频播放位置对应的检测结果 (由 drawLoop 统一更新)
  const [playbackDetections, setPlaybackDetections] = useState<TrackedPlateResult[]>([]);
  const [playbackTimestamp, setPlaybackTimestamp] = useState<number>(0);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const animFrameRef = useRef<number>(0);
  const latestProcessedRef = useRef<number>(0);
  const lastValidTrackRef = useRef<TrackedPlateResult[]>([]);
  const lastValidTrackTimeRef = useRef<number>(0);
  const lastSyncRef = useRef<number>(0);

  // ── Stream 模式 refs ──
  const streamDetectionsRef = useRef<TrackedPlateResult[]>([]);
  const streamImgRef = useRef<HTMLImageElement>(null);
  const streamCanvasRef = useRef<HTMLCanvasElement>(null);
  const streamAnimFrameRef = useRef<number>(0);
  const lastValidStreamRef = useRef<TrackedPlateResult[]>([]);

  // ── Stream 模式状态 ──
  const [streamUrl, setStreamUrl] = useState('');
  const [streamName, setStreamName] = useState('');
  const [streamImgSrc, setStreamImgSrc] = useState<string | null>(null);
  const [streamSessionId, setStreamSessionId] = useState<string | null>(null);
  const [streamRunning, setStreamRunning] = useState(false);
  const [streamPlateSummary, setStreamPlateSummary] = useState<TrackedPlateSummary[]>([]);
  const [streamDetections, setStreamDetections] = useState<TrackedPlateResult[]>([]);

  // ═══════════════════════════════════════════════════════════
  //  图像模式 (保持不变)
  // ═══════════════════════════════════════════════════════════

  const handleImageUpload = async (file: File) => {
    setLoading(true);
    setResults([]);
    setImageScale({ x: 1, y: 1 });

    const video = isVideoFile(file);
    setIsVideo(video);

    const reader = new FileReader();
    reader.onload = (e) => setPreviewUrl(e.target?.result as string);
    reader.readAsDataURL(file);

    try {
      const res = await uploadPlateImage(file);
      if (res.data.code === 200) {
        setResults(res.data.data);
        message.success(res.data.message || '识别完成');
      } else {
        message.error(res.data.message || '识别失败');
      }
    } catch {
      message.error('请求失败, 请检查后端服务是否已启动');
    } finally {
      setLoading(false);
    }
    return false;
  };

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    setImageScale({
      x: img.clientWidth / img.naturalWidth,
      y: img.clientHeight / img.naturalHeight,
    });
  };

  // ═══════════════════════════════════════════════════════════
  //  追踪模式 — 视频上传 + WebSocket
  // ═══════════════════════════════════════════════════════════

  const wsBaseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

  const connectWs = useCallback((sessionId: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    setWsStatus('connecting');
    const url = `${wsBaseUrl}/api/ws/plate/track/${sessionId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus('connected');
      message.success('已连接实时追踪服务');
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsPlateMessage = JSON.parse(event.data);

        switch (msg.type) {
          case 'detection': {
            const det = msg as FrameDetection;

            // 按实际 timestamp 建立索引 (用于 Canvas 和面板的播放同步)
            const ts = det.timestamp;
            // 追踪最新处理到的帧时间戳 (用于计算 lag)
            if (ts > latestProcessedRef.current) {
              latestProcessedRef.current = ts;
            }
            setTimeIndexedDetections((prev) => {
              const next = new Map(prev);
              next.set(ts, det.detections);
              return next;
            });
            // 有序帧数组: 按 timestamp 升序追加 (后端推流顺序保证有序)
            detectionFramesRef.current.push({ timestamp: ts, detections: det.detections });

            // 记录检测日志
            if (det.detections.length > 0) {
              setDetectionLog((prev) => [
                ...prev.slice(-99),
                {
                  time: ts,
                  count: det.detections.length,
                  plateNos: det.detections.map((d) => d.plateNo),
                },
              ]);
            }
            break;
          }
          case 'status': {
            const st = msg as SessionStatusMsg;
            setTrackProgress(st.progress);
            setTrackProcessedFrames(st.framesProcessed);
            setTrackTotalFrames(st.totalFrames);
            setTrackStatusMsg(st.status);
            break;
          }
          case 'summary': {
            const sm = msg as TrackingSummary;
            setTrackedPlates(sm.plates);
            setTrackDuration(sm.duration);
            setTrackStatusMsg('completed');
            message.success(`追踪完成! 共识别到 ${sm.plates.length} 个车牌`);
            break;
          }
          case 'error': {
            message.error(msg.message);
            setTrackStatusMsg('error');
            break;
          }
        }
      } catch (e) {
        console.warn('WebSocket 消息解析失败:', e);
      }
    };

    ws.onerror = () => {
      setWsStatus('disconnected');
      if (wsStatus !== 'disconnected') {
        message.warning('WebSocket 连接失败');
      }
    };

    ws.onclose = () => {
      setWsStatus('disconnected');
      wsRef.current = null;
    };
  }, [wsBaseUrl]);

  // 通过 WebSocket 向后端发送播放控制消息 (播放驱动追踪)
  const sendSync = useCallback((type: string, currentTime?: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type,
        currentTime: currentTime ?? videoRef.current?.currentTime ?? 0,
      }));
    }
  }, []);

  const handleTrackUpload = async (file: File) => {
    if (!isVideoFile(file)) {
      message.warning('追踪模式仅支持视频文件');
      return false;
    }

    setTrackLoading(true);
    setTrackedPlates([]);
    setTimeIndexedDetections(new Map());
    detectionFramesRef.current = [];
    setPlaybackDetections([]);
    setPlaybackTimestamp(0);
    latestProcessedRef.current = 0;
    lastValidTrackRef.current = [];
    lastValidTrackTimeRef.current = 0;
    lastSyncRef.current = 0;
    setDetectionLog([]);
    setTrackProgress(0);
    setTrackStatusMsg('uploading');
    setTrackSessionId(null);

    // 创建本地视频预览
    const reader = new FileReader();
    reader.onload = (e) => setPreviewUrl(e.target?.result as string);
    reader.readAsDataURL(file);

    try {
      const res = await uploadTrackVideo(file);
      if (res.data.code === 200) {
        const { sessionId } = res.data.data;
        setTrackSessionId(sessionId);
        setTrackTotalFrames(res.data.data.totalFrames);
        setTrackStatusMsg('connecting');

        // 连接 WebSocket
        connectWs(sessionId);
      } else {
        message.error(res.data.message || '上传失败');
        setTrackLoading(false);
      }
    } catch {
      message.error('请求失败, 请检查后端服务');
      setTrackLoading(false);
    } finally {
      setTrackLoading(false);
    }
    return false;
  };

  // 画布绘制循环 (视频 + canvas overlay + 检测面板同步)
  // 始终使用最近帧的完整渲染，永不闪烁
  const drawLoop = useCallback(() => {
    if (!canvasRef.current || !videoRef.current) return;
    const video = videoRef.current;
    if (video.ended) {
      animFrameRef.current = requestAnimationFrame(drawLoop);
      return;
    }

    const currentTime = video.currentTime;
    // 总是找最近帧（不设 maxDiff）
    const matched = findNearestFrame(detectionFramesRef.current, currentTime);

    if (matched && matched.detections.length > 0) {
      lastValidTrackRef.current = matched.detections;
      lastValidTrackTimeRef.current = currentTime;
      drawDetectionsOnCanvas(canvasRef.current, video, matched.detections);
      setPlaybackDetections(matched.detections);
      setPlaybackTimestamp(matched.timestamp);
    } else if (lastValidTrackRef.current.length > 0 &&
               currentTime - lastValidTrackTimeRef.current < 1.5) {
      // 1.5s 内无新检测时保留上次框，超过则清除（防止车牌消失后框图）
      drawDetectionsOnCanvas(canvasRef.current, video, lastValidTrackRef.current);
    } else if (lastValidTrackRef.current.length > 0) {
      // 超时 1.5s：清除残留框
      lastValidTrackRef.current = [];
      const ctx = canvasRef.current.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
      setPlaybackDetections([]);
    } else {
      const ctx = canvasRef.current.getContext('2d');
      if (ctx) {
        ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
      }
    }

    animFrameRef.current = requestAnimationFrame(drawLoop);
  }, []); // 使用 ref 而非 state 依赖, 避免循环重绘

  useEffect(() => {
    if (mode === 'track' && previewUrl && wsStatus === 'connected') {
      animFrameRef.current = requestAnimationFrame(drawLoop);
    }
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
    // drawLoop 使用 ref 不依赖 state, 故只依赖 mode/previewUrl/wsStatus
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, previewUrl, wsStatus]);

  // ═══════════════════════════════════════════════════════════
  //  Stream 画布绘制循环
  // ═══════════════════════════════════════════════════════════
  //  Stream 画布绘制循环
  // ═══════════════════════════════════════════════════════════

  const streamDrawLoop = useCallback(() => {
    if (!streamCanvasRef.current || !streamImgRef.current) return;
    const img = streamImgRef.current;
    const detections = streamDetectionsRef.current;

    const ctx = streamCanvasRef.current.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = img.getBoundingClientRect();
    streamCanvasRef.current.width = rect.width * dpr;
    streamCanvasRef.current.height = rect.height * dpr;
    streamCanvasRef.current.style.width = `${rect.width}px`;
    streamCanvasRef.current.style.height = `${rect.height}px`;
    ctx.scale(dpr, dpr);

    // 清空画布
    ctx.clearRect(0, 0, rect.width, rect.height);

    // 图像可能还未加载完成
    if (!img.naturalWidth || !img.naturalHeight) {
      streamAnimFrameRef.current = requestAnimationFrame(streamDrawLoop);
      return;
    }

    // 决定画什么: 当前检测 or 上次有效的检测
    const drawTarget = detections.length > 0 ? detections : lastValidStreamRef.current;
    const isStale = detections.length === 0;

    if (drawTarget.length === 0) {
      streamAnimFrameRef.current = requestAnimationFrame(streamDrawLoop);
      return;
    }

    // 有有效检测 → 更新缓存
    if (!isStale) {
      lastValidStreamRef.current = detections;
    }

    const scaleX = rect.width / img.naturalWidth;
    const scaleY = rect.height / img.naturalHeight;

    if (isStale) ctx.globalAlpha = 0.35;

    for (const d of drawTarget) {
      const x = d.bbox.x * scaleX;
      const y = d.bbox.y * scaleY;
      const w = d.bbox.width * scaleX;
      const h = d.bbox.height * scaleY;
      const color = getColorForPlate(d.color);

      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.strokeRect(x, y, w, h);

      const label = `${d.plateNo}`;
      ctx.font = 'bold 14px -apple-system, sans-serif';
      const tw = ctx.measureText(label).width;

      const labelY = y > 30 ? y - 8 : y + h + 8;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.roundRect(x, labelY - 24, tw + 16, 24, 4);
      ctx.fill();

      ctx.fillStyle = '#fff';
      ctx.fillText(label, x + 8, labelY - 7);

      const info = `#${d.trackId} · ${d.color} · ${(d.confidence * 100).toFixed(0)}%`;
      ctx.font = '11px -apple-system, sans-serif';
      const infoY = y > 30 ? y - 36 : y + h + 36;
      ctx.fillStyle = color;
      ctx.fillText(info, x, infoY);
    }

    if (isStale) ctx.globalAlpha = 1.0;

    streamAnimFrameRef.current = requestAnimationFrame(streamDrawLoop);
  }, []);

  // 启动/停止 Stream 画布循环
  useEffect(() => {
    if (wsStatus === 'connected' && streamSessionId && mode === 'stream') {
      streamAnimFrameRef.current = requestAnimationFrame(streamDrawLoop);
    }
    return () => {
      if (streamAnimFrameRef.current) {
        cancelAnimationFrame(streamAnimFrameRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsStatus, streamSessionId, mode]);

  // 清理
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      if (streamAnimFrameRef.current) {
        cancelAnimationFrame(streamAnimFrameRef.current);
      }
    };
  }, []);

  // ═══════════════════════════════════════════════════════════
  //  流模式
  // ═══════════════════════════════════════════════════════════

  const connectStreamWs = useCallback((sessionId: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    setWsStatus('connecting');
    const url = `${wsBaseUrl}/api/ws/plate/track/${sessionId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus('connected');
      setStreamRunning(true);
      message.success('流追踪已启动');
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsPlateMessage = JSON.parse(event.data);

        switch (msg.type) {
          case 'detection': {
            const det = msg as FrameDetection;
            setStreamDetections(det.detections);
            streamDetectionsRef.current = det.detections;
            break;
          }
          case 'status': {
            const st = msg as SessionStatusMsg;
            setTrackProgress(st.progress);
            setTrackProcessedFrames(st.framesProcessed);
            break;
          }
          case 'summary': {
            const sm = msg as TrackingSummary;
            setStreamPlateSummary(sm.plates);
            setStreamRunning(false);
            message.success(`流追踪完成! 共识别 ${sm.plates.length} 个车牌`);
            break;
          }
          case 'error': {
            message.error(msg.message);
            setStreamRunning(false);
            break;
          }
        }
      } catch (e) {
        console.warn('WebSocket 消息解析失败:', e);
      }
    };

    ws.onerror = () => {
      setWsStatus('disconnected');
      setStreamRunning(false);
      message.warning('流追踪连接失败, 请确认后端已启动');
    };

    ws.onclose = () => {
      setWsStatus('disconnected');
      setStreamRunning(false);
      wsRef.current = null;
    };
  }, [wsBaseUrl]);

  const handleStreamStart = async () => {
    if (!streamUrl.trim()) {
      message.warning('请输入流地址');
      return;
    }

    setStreamRunning(true);
    setStreamPlateSummary([]);
    setStreamDetections([]);
    lastValidStreamRef.current = [];
    setTrackProgress(0);
    setStreamImgSrc(null);

    try {
      const res = await startStreamTracking(streamUrl.trim(), streamName.trim() || undefined);
      if (res.data.code === 200) {
        const { sessionId } = res.data.data;
        setStreamSessionId(sessionId);
        connectStreamWs(sessionId);
      } else {
        message.error(res.data.message || '启动失败');
        setStreamRunning(false);
      }
    } catch {
      message.error('无法连接到后端服务');
      setStreamRunning(false);
    }
  };

  const handleStreamStop = async () => {
    if (streamSessionId) {
      try {
        await stopStreamTracking(streamSessionId);
      } catch { /* ignore */ }
    }
    if (wsRef.current) {
      wsRef.current.close();
    }
    setStreamRunning(false);
    setWsStatus('disconnected');
    message.info('流追踪已停止');
  };

  // ═══════════════════════════════════════════════════════════
  //  表格列定义
  // ═══════════════════════════════════════════════════════════

  const uploadColumns = [
    { title: '车辆编号', dataIndex: 'carId', key: 'carId', width: 90 },
    {
      title: '车型', dataIndex: 'vehicleType', key: 'vehicleType', width: 100,
      render: (t: string) => {
        const info = VEHICLE_TYPE_MAP[t] || VEHICLE_TYPE_MAP.unknown;
        return <Tag color={info.color}>{info.icon} {info.label}</Tag>;
      },
    },
    {
      title: '车牌号码', dataIndex: 'plateNo', key: 'plateNo',
      render: (text: string) => (
        <Tag color="blue" style={{ fontSize: 16, fontWeight: 600 }}>{text}</Tag>
      ),
    },
    {
      title: '颜色', dataIndex: 'color', key: 'color',
      render: (c: string) => {
        const info = PLATE_COLOR_MAP[c];
        return <Tag color={info?.color || 'default'}>{info?.label || c}</Tag>;
      },
    },
    {
      title: '时间(秒)', dataIndex: 'timestamp', key: 'timestamp', width: 100,
      render: (v: number) => v != null ? `${v.toFixed(1)}s` : '-',
    },
    {
      title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 100,
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
  ];

  const trackColumns = [
    {
      title: 'ID', dataIndex: 'trackId', key: 'trackId', width: 70,
    },
    {
      title: '车型', dataIndex: 'vehicleType', key: 'vehicleType', width: 90,
      render: (t: string) => {
        const info = VEHICLE_TYPE_MAP[t] || VEHICLE_TYPE_MAP.unknown;
        return <Tag color={info.color}>{info.icon}</Tag>;
      },
    },
    {
      title: '车牌号码', dataIndex: 'plateNo', key: 'plateNo',
      render: (text: string) => (
        <Tag color="blue" style={{ fontSize: 15, fontWeight: 600 }}>{text}</Tag>
      ),
    },
    {
      title: '颜色', dataIndex: 'color', key: 'color', width: 80,
      render: (c: string) => {
        const info = PLATE_COLOR_MAP[c];
        return <Tag color={info?.color || 'default'}>{info?.label || c}</Tag>;
      },
    },
    {
      title: '首次出现', dataIndex: 'firstSeen', key: 'firstSeen', width: 100,
      render: (v: number) => `${v.toFixed(1)}s`,
    },
    {
      title: '末次出现', dataIndex: 'lastSeen', key: 'lastSeen', width: 100,
      render: (v: number) => `${v.toFixed(1)}s`,
    },
    {
      title: '出现次数', dataIndex: 'appearances', key: 'appearances', width: 90,
    },
    {
      title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 90,
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
  ];

  const detectionLogColumns = [
    { title: '时间(秒)', dataIndex: 'time', key: 'time', width: 100, render: (v: number) => `${v.toFixed(1)}s` },
    { title: '检测数', dataIndex: 'count', key: 'count', width: 80 },
    {
      title: '车牌号', dataIndex: 'plateNos', key: 'plateNos',
      render: (nos: string[]) => (
        <Space size={4} wrap>
          {nos.map((n, i) => <Tag key={i} color="blue">{n}</Tag>)}
        </Space>
      ),
    },
  ];

  // ═══════════════════════════════════════════════════════════
  //  渲染: 状态彩色标签
  // ═══════════════════════════════════════════════════════════

  const renderWsBadge = () => {
    const map: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
      connected: { color: 'green', text: '已连接', icon: <CheckCircleOutlined /> },
      connecting: { color: 'orange', text: '连接中', icon: <LoadingOutlined /> },
      disconnected: { color: 'default', text: '未连接', icon: <CloseCircleOutlined /> },
    };
    const s = map[wsStatus];
    return <Badge status={s.color as any} text={<><span style={{ marginRight: 4 }}>{s.icon}</span>{s.text}</>} />;
  };

  const renderProgress = () => {
    const pct = Math.round(trackProgress * 100);
    return (
      <div style={{ marginBottom: 16 }}>
        <Progress
          percent={pct}
          status={trackStatusMsg === 'error' ? 'exception' : trackStatusMsg === 'completed' ? 'success' : 'active'}
          format={() => `${trackProcessedFrames}/${trackTotalFrames} 帧`}
        />
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════════
  //  TAB 内容
  // ═══════════════════════════════════════════════════════════

  const uploadTab = (
    <div>
      <Card style={{ marginBottom: 24 }}>
        <Dragger
          accept="image/*,video/*"
          showUploadList={false}
          beforeUpload={handleImageUpload}
          disabled={loading}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽图片/视频到此处上传</p>
          <p className="ant-upload-hint">支持 JPG、PNG、MP4、AVI、MOV 等格式</p>
        </Dragger>
      </Card>

      {previewUrl && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <Card title={isVideo ? '视频预览' : '图片预览'} style={{ flex: '1 1 400px' }}>
            {isVideo ? (
              <video src={previewUrl} controls style={{ maxWidth: '100%', maxHeight: 400, borderRadius: 8 }} />
            ) : (
              <div style={{ position: 'relative', display: 'inline-block' }}>
                <img
                  src={previewUrl} alt="preview"
                  style={{ maxWidth: '100%', maxHeight: 400, borderRadius: 8 }}
                  onLoad={handleImageLoad}
                />
                {results.map((r) => (
                  <div
                    key={r.carId}
                    style={{
                      position: 'absolute',
                      left: r.bbox.x * imageScale.x,
                      top: r.bbox.y * imageScale.y,
                      width: r.bbox.width * imageScale.x,
                      height: r.bbox.height * imageScale.y,
                      border: '2px solid #1677ff', borderRadius: 4, pointerEvents: 'none',
                    }}
                  >
                    <span style={{
                      position: 'absolute', top: -24, left: 0,
                      background: '#1677ff', color: '#fff',
                      padding: '2px 8px', borderRadius: 4, fontSize: 12, whiteSpace: 'nowrap',
                    }}>
                      {r.plateNo} · {VEHICLE_TYPE_MAP[r.vehicleType]?.label || r.vehicleType}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="识别结果" style={{ flex: '1 1 300px', minWidth: 300 }}>
            {results.length > 0 ? (
              <Table columns={uploadColumns} dataSource={results} rowKey="carId" pagination={false} size="small" />
            ) : (
              <Empty description="未识别到车牌" />
            )}
          </Card>
        </div>
      )}

      {!previewUrl && <Card><Empty description="请先上传图片或视频开始识别" /></Card>}
    </div>
  );

  const trackTab = (
    <div>
      <Card style={{ marginBottom: 24 }}>
        <Dragger
          accept="video/*"
          showUploadList={false}
          beforeUpload={handleTrackUpload}
          disabled={trackLoading || wsStatus === 'connecting' || wsStatus === 'connected'}
        >
          {trackLoading ? (
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <Spin indicator={<LoadingOutlined style={{ fontSize: 36, marginBottom: 12 }} />} />
              <p style={{ fontSize: 15, color: '#1677ff' }}>正在上传视频...</p>
            </div>
          ) : (
            <>
          <p className="ant-upload-drag-icon"><VideoCameraOutlined /></p>
          <p className="ant-upload-text">点击或拖拽视频到此处开始实时追踪</p>
          <p className="ant-upload-hint">上传后自动连接 WebSocket, 实时显示检测结果</p>
            </>
          )}
        </Dragger>
      </Card>

      {/* 连接状态 */}
      {trackSessionId && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
            <Space>
              <Text strong>会话:</Text>
              <Text code>{trackSessionId}</Text>
            </Space>
            <Space>
              <Text>连接状态:</Text>
              {renderWsBadge()}
              {wsStatus === 'connected' && (
                <Text type="secondary" style={{ fontSize: 12 }}>已处理 {trackProcessedFrames} 帧</Text>
              )}
            </Space>
          </div>
        </Card>
      )}

      {/* 视频 + 检测结果 */}
      {previewUrl && wsStatus === 'connected' && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          {/* 视频 + Canvas 叠加 */}
          <Card
            title={
              <Space>
                <span>实时追踪</span>
              </Space>
            }
            style={{ flex: '1 1 500px' }}
          >
            <div style={{ position: 'relative' }}>
              <video
                ref={videoRef}
                src={previewUrl}
                controls
                onPlay={() => sendSync('play')}
                onPause={() => sendSync('pause')}
                onSeeked={() => sendSync('seek')}
                onTimeUpdate={() => {
                  // 播放中每 300ms 同步一次位置
                  const now = Date.now();
                  if (!videoRef.current?.paused && now - lastSyncRef.current > 300) {
                    lastSyncRef.current = now;
                    sendSync('sync');
                  }
                }}
                style={{ maxWidth: '100%', maxHeight: 450, borderRadius: 8, display: 'block' }}
              />
              <canvas
                ref={canvasRef}
                style={{
                  position: 'absolute', top: 0, left: 0,
                  width: '100%', height: '100%',
                  pointerEvents: 'none',
                  borderRadius: 8,
                }}
              />
            </div>
          </Card>

          {/* 实时检测面板 */}
          <div style={{ flex: '1 1 350px', display: 'flex', flexDirection: 'column', gap: 16, minWidth: 300 }}>
            {/* 当前帧检测 — 与 Canvas 同步 */}
            <Card title={`当前帧 @${playbackTimestamp.toFixed(1)}s (${playbackDetections.length} 个)`} size="small">
              {playbackDetections.length > 0 ? (
                <Space direction="vertical" style={{ width: '100%' }}>
                  {playbackDetections.map((d) => (
                    <div
                      key={d.trackId}
                      style={{
                        display: 'flex', justifyContent: 'space-between',
                        alignItems: 'center', padding: '4px 8px',
                        background: '#f6f8fa', borderRadius: 4,
                      }}
                    >
                      <Space>
                        <Tag color="blue">#{d.trackId}</Tag>
                        <Text strong style={{ fontSize: 15 }}>{d.plateNo}</Text>
                        <Tag color={PLATE_COLOR_MAP[d.color]?.color}>
                          {PLATE_COLOR_MAP[d.color]?.label || d.color}
                        </Tag>
                        {d.vehicleType && VEHICLE_TYPE_MAP[d.vehicleType] && (
                          <Text type="secondary">{VEHICLE_TYPE_MAP[d.vehicleType].icon} {VEHICLE_TYPE_MAP[d.vehicleType].label}</Text>
                        )}
                      </Space>
                      <Text type="secondary">{(d.confidence * 100).toFixed(0)}%</Text>
                    </div>
                  ))}
                </Space>
              ) : detectionFramesRef.current.length === 0 ? (
                <Text type="secondary">等待检测结果...</Text>
              ) : (
                <Text type="secondary">该时间点无检测结果</Text>
              )}
            </Card>

            {/* 实时日志 — 高亮当前播放位置的条目 */}
            <Card title={`检测日志 (${detectionLog.length})`} size="small" style={{ flex: 1 }}>
              {detectionLog.length > 0 ? (
                <div style={{ maxHeight: 200, overflow: 'auto' }}>
                  <Table
                    columns={detectionLogColumns}
                    dataSource={detectionLog.map((d, i) => ({ ...d, key: i, _time: d.time }))}
                    pagination={false}
                    size="small"
                    rowClassName={(record) => {
                      const diff = Math.abs((record as any)._time - playbackTimestamp);
                      return diff < 0.5 ? 'current-playback-row' : '';
                    }}
                  />
                </div>
              ) : (
                <Text type="secondary">等待检测数据...</Text>
              )}
            </Card>
          </div>
        </div>
      )}

      {/* 追踪汇总 */}
      {trackedPlates.length > 0 && (
        <Card title={`追踪汇总 (${trackedPlates.length} 个车牌)`} style={{ marginTop: 24 }}>
          <Table
            columns={trackColumns}
            dataSource={trackedPlates}
            rowKey="trackId"
            pagination={false}
            size="small"
          />
        </Card>
      )}

      {!previewUrl && !trackSessionId && (
        <Card><Empty description="上传视频开始实时车牌追踪" icon={<VideoCameraOutlined />} /></Card>
      )}
    </div>
  );

  const streamTab = (
    <div>
      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 250 }}>
            <Text strong>流媒体地址</Text>
            <Input
              placeholder="rtsp://localhost:8554/camera  或   rtmp://..."
              prefix={<LinkOutlined />}
              value={streamUrl}
              onChange={(e) => setStreamUrl(e.target.value)}
              size="large"
              disabled={streamRunning}
            />
          </div>
          <div style={{ minWidth: 150 }}>
            <Text strong>名称 (可选)</Text>
            <Input
              placeholder="前摄像头"
              value={streamName}
              onChange={(e) => setStreamName(e.target.value)}
              size="large"
              disabled={streamRunning}
            />
          </div>
          <Button
            type="primary"
            icon={streamRunning ? <StopOutlined /> : <PlayCircleOutlined />}
            size="large"
            onClick={streamRunning ? handleStreamStop : handleStreamStart}
            danger={streamRunning}
          >
            {streamRunning ? '停止追踪' : '启动追踪'}
          </Button>
        </div>

        <div style={{ marginTop: 16 }}>
          <Alert
            type="info"
            message="需要配合 MediaMTX + FFmpeg 使用"
            description={
              <ol style={{ margin: '4px 0', paddingLeft: 20 }}>
                <li>启动 MediaMTX 流媒体服务器</li>
                <li>使用 FFmpeg 推送摄像头流: <Text code>ffmpeg -f dshow -i video="摄像头" -f rtsp rtsp://localhost:8554/camera</Text></li>
                <li>在上方输入流地址, 点击"启动追踪"</li>
              </ol>
            }
            showIcon
          />
        </div>
      </Card>

      {/* 连接状态 + 进度 */}
      {streamSessionId && wsStatus === 'connected' && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
            <Space>
              <Text strong>会话:</Text>
              <Text code>{streamSessionId}</Text>
            </Space>
            <Space>
              <Text>状态:</Text>
              {renderWsBadge()}
              <Text type="secondary">已处理 {trackProcessedFrames} 帧</Text>
            </Space>
          </div>
        </Card>
      )}

      {/* 实时视频 + 检测面板 */}
      {wsStatus === 'connected' && streamSessionId && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          {/* 视频播放区: MJPEG 流 + Canvas 覆盖层 */}
          <Card
            title="实时视频"
            style={{ flex: '1 1 500px' }}
            extra={
              <Badge status="processing" text={`已处理 ${trackProcessedFrames} 帧`} />
            }
          >
            <div style={{ position: 'relative' }}>
              <img
                ref={streamImgRef}
                src={`/api/plate/stream/${streamSessionId}/mjpeg${''}`}
                alt="实时流"
                style={{ maxWidth: '100%', maxHeight: 450, borderRadius: 8, display: 'block' }}
                onLoad={() => {
                  // 确保 canvas 尺寸同步
                  if (streamCanvasRef.current && streamImgRef.current) {
                    const rect = streamImgRef.current.getBoundingClientRect();
                    const dpr = window.devicePixelRatio || 1;
                    streamCanvasRef.current.width = rect.width * dpr;
                    streamCanvasRef.current.height = rect.height * dpr;
                    streamCanvasRef.current.style.width = `${rect.width}px`;
                    streamCanvasRef.current.style.height = `${rect.height}px`;
                  }
                }}
              />
              <canvas
                ref={streamCanvasRef}
                style={{
                  position: 'absolute', top: 0, left: 0,
                  width: '100%', height: '100%',
                  pointerEvents: 'none', borderRadius: 8,
                }}
              />
            </div>
          </Card>

          {/* 检测结果面板 */}
          <div style={{ flex: '1 1 350px', minWidth: 300 }}>
            <Card title={`实时检测 (${streamDetections.length} 个)`}>
              {streamDetections.length > 0 ? (
                <Space direction="vertical" style={{ width: '100%' }}>
                  {streamDetections.map((d) => (
                    <div
                      key={d.trackId}
                      style={{
                        display: 'flex', justifyContent: 'space-between',
                        alignItems: 'center', padding: '8px 12px',
                        background: '#f6f8fa', borderRadius: 6,
                        border: `2px solid ${getColorForPlate(d.color)}`,
                      }}
                    >
                      <Space>
                        <Tag color="blue">#{d.trackId}</Tag>
                        <Text strong style={{ fontSize: 16 }}>{d.plateNo}</Text>
                        <Tag color={PLATE_COLOR_MAP[d.color]?.color}>
                          {PLATE_COLOR_MAP[d.color]?.label || d.color}
                        </Tag>
                      </Space>
                      <Text type="secondary">{(d.confidence * 100).toFixed(0)}%  {VEHICLE_TYPE_MAP[d.vehicleType]?.icon}</Text>
                    </div>
                  ))}
                </Space>
              ) : (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin indicator={<LoadingOutlined style={{ fontSize: 32 }} />} />
                  <div style={{ marginTop: 16 }}><Text type="secondary">等待流数据...</Text></div>
                </div>
              )}
            </Card>

            {/* 汇总 */}
            {streamPlateSummary.length > 0 && (
              <Card title={`追踪汇总 (${streamPlateSummary.length} 个车牌)`} style={{ marginTop: 16 }}>
                <Table
                  columns={trackColumns}
                  dataSource={streamPlateSummary}
                  rowKey="trackId"
                  pagination={false}
                  size="small"
                />
              </Card>
            )}
          </div>
        </div>
      )}

      {wsStatus === 'disconnected' && !streamRunning && (
        <Card><Empty description="输入流地址并启动追踪, 实时检测车牌" icon={<LinkOutlined />} /></Card>
      )}
    </div>
  );

  // ═══════════════════════════════════════════════════════════
  //  Tabs 配置
  // ═══════════════════════════════════════════════════════════

  const tabItems = [
    {
      key: 'upload',
      label: <span><InboxOutlined /> 图片/视频上传</span>,
      children: uploadTab,
    },
    {
      key: 'track',
      label: (
        <span>
          <VideoCameraOutlined /> 实时追踪
          {wsStatus === 'connected' && <Badge status="processing" color="green" style={{ marginLeft: 6 }} />}
        </span>
      ),
      children: trackTab,
    },
    {
      key: 'stream',
      label: <span><LinkOutlined /> 流媒体输入</span>,
      children: streamTab,
    },
  ];

  return (
    <div>
      <PageHeader
        title="车牌识别"
        subtitle="上传道路图片/视频或接入流媒体, 自动检测并实时追踪车牌信息"
        extra={
          <Space>
            {wsStatus === 'connected' && renderWsBadge()}
          </Space>
        }
      />

      {/* 检测日志高亮样式 */}
      <style>{`
        .current-playback-row {
          background: #e6f4ff !important;
          transition: background 0.15s;
        }
        .current-playback-row td {
          background: #e6f4ff !important;
        }
      `}</style>

      <Tabs
        activeKey={mode}
        onChange={(k) => setMode(k as PageMode)}
        items={tabItems}
        tabBarStyle={{ marginBottom: 20 }}
      />
    </div>
  );
};

export default PlateRecognition;
