import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Card,
  Descriptions,
  Empty,
  Progress,
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
  recognizePoliceGestureFrame,
  resetPoliceGestureStream,
  uploadPoliceGestureVideo,
} from '../api';

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
  gesture: string;
  gestureId: number;
  confidence: number;
};

type Segment = {
  start: number;
  end: number;
  gesture: string;
  gestureId: number;
};

type StreamRecord = PoliceGestureResult & {
  inference_ms?: number;
};

const STREAM_ID = 'web-camera-police-gesture';
const STREAM_INTERVAL_MS = 1200;

const getGestureLabel = (gestureId?: number, fallback?: string) => (
  gestureId === undefined ? '等待识别' : GESTURE_LABELS[gestureId] || fallback || '未知'
);

const PoliceGesture: React.FC = () => {
  const [result, setResult] = useState<PoliceGestureResult | null>(null);
  const [top5, setTop5] = useState<Array<{ gesture: string; gestureId: number; confidence: number }>>([]);
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [inferenceMs, setInferenceMs] = useState<number>(0);
  const [frames, setFrames] = useState<FrameResult[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [duration, setDuration] = useState<number>(0);
  const [fps, setFps] = useState<number>(0);
  const [sampleFps, setSampleFps] = useState<number>(0);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [streaming, setStreaming] = useState(false);
  const [streamResult, setStreamResult] = useState<StreamRecord | null>(null);
  const [streamHistory, setStreamHistory] = useState<StreamRecord[]>([]);
  const [streamBusy, setStreamBusy] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | undefined>(undefined);

  const currentSegment = useMemo(() => (
    segments.find((seg) => playbackTime >= seg.start && playbackTime <= seg.end)
  ), [playbackTime, segments]);

  const currentFrame = useMemo(() => {
    if (!frames.length) return undefined;
    return frames.reduce((closest, frame) => (
      Math.abs(frame.time - playbackTime) < Math.abs(closest.time - playbackTime) ? frame : closest
    ), frames[0]);
  }, [frames, playbackTime]);

  const overlayGestureId = currentSegment?.gestureId ?? currentFrame?.gestureId;
  const overlayLabel = overlayGestureId !== undefined
    ? getGestureLabel(overlayGestureId, currentSegment?.gesture || currentFrame?.gesture)
    : loading
      ? '正在分析'
      : '等待标注';
  const overlayColor = overlayGestureId !== undefined ? GESTURE_COLORS[overlayGestureId] : '#8c8c8c';

  const handleUpload = async (file: File) => {
    setLoading(true);
    setProgress(0);
    setResult(null);
    setTop5([]);
    setFrames([]);
    setSegments([]);
    setInferenceMs(0);
    setDuration(0);
    setFps(0);
    setSampleFps(0);
    setPlaybackTime(0);

    if (videoSrc) {
      URL.revokeObjectURL(videoSrc);
    }
    const objectUrl = URL.createObjectURL(file);
    setVideoSrc(objectUrl);

    const progressTimer = window.setInterval(() => {
      setProgress((p) => {
        if (p >= 90) {
          window.clearInterval(progressTimer);
          return 90;
        }
        return p + 3;
      });
    }, 200);

    try {
      const response = await uploadPoliceGestureVideo(file);
      const data = (response.data as any).data || response.data;

      window.clearInterval(progressTimer);
      setProgress(100);
      setResult({
        gesture: data.gesture,
        gestureId: data.gestureId,
        confidence: data.confidence,
        timestamp: data.timestamp,
      });
      setTop5(data.top5 || []);
      setInferenceMs(data.inference_ms || 0);
      setFrames(data.frames || []);
      setSegments(data.segments || []);
      setDuration(data.video_duration || videoRef.current?.duration || 0);
      setFps(data.video_fps || 0);
      setSampleFps(data.sample_fps || 0);
      message.success(`识别完成：${getGestureLabel(data.gestureId, data.gesture)}`);
    } catch (error) {
      window.clearInterval(progressTimer);
      setProgress(0);
      console.error('police gesture upload failed:', error);
      message.error('识别失败，请确认后端服务已启动');
    }

    setLoading(false);
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
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (cameraRef.current) {
      cameraRef.current.srcObject = null;
    }
    setStreaming(false);
    setStreamBusy(false);
    await resetPoliceGestureStream(STREAM_ID).catch(() => undefined);
  }, []);

  const captureAndRecognize = useCallback(async () => {
    if (!cameraRef.current || !canvasRef.current || streamBusy) return;
    const video = cameraRef.current;
    if (!video.videoWidth || !video.videoHeight) return;

    setStreamBusy(true);
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      setStreamBusy(false);
      return;
    }

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(async (blob) => {
      if (!blob) {
        setStreamBusy(false);
        return;
      }

      try {
        const response = await recognizePoliceGestureFrame(blob, STREAM_ID);
        const data = ((response.data as any).data || response.data) as StreamRecord;
        setStreamResult(data);
        setStreamHistory((items) => [data, ...items].slice(0, 10));
      } catch (error) {
        console.error('stream frame failed:', error);
        message.warning('实时帧识别失败，请检查后端服务');
      } finally {
        setStreamBusy(false);
      }
    }, 'image/jpeg', 0.78);
  }, [streamBusy]);

  const startCamera = async () => {
    try {
      await resetPoliceGestureStream(STREAM_ID);
      const media = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'environment' },
        audio: false,
      });
      streamRef.current = media;
      if (cameraRef.current) {
        cameraRef.current.srcObject = media;
        await cameraRef.current.play();
      }
      setStreamResult(null);
      setStreamHistory([]);
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
      if (timerRef.current) window.clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (videoSrc) URL.revokeObjectURL(videoSrc);
    };
  }, [videoSrc]);

  const streamLabel = getGestureLabel(streamResult?.gestureId, streamResult?.gesture);
  const streamColor = streamResult ? GESTURE_COLORS[streamResult.gestureId] : '#8c8c8c';

  return (
    <div>
      <PageHeader
        title="交警手势识别"
        subtitle="基于人体关键点和 LSTM 时序特征识别 8 种中国标准交警指挥手势"
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

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 1.3fr) minmax(320px, 0.7fr)', gap: 16 }}>
        <Card
          title="上传视频预览"
          extra={videoSrc && <Tag color={loading ? 'processing' : segments.length ? 'green' : 'default'}>{loading ? '分析中' : segments.length ? `${segments.length} 段动作` : '待分析'}</Tag>}
        >
          {videoSrc ? (
            <div style={{ position: 'relative', background: '#000', borderRadius: 8, overflow: 'hidden' }}>
              <video
                ref={videoRef}
                src={videoSrc}
                controls
                onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || duration)}
                onTimeUpdate={(event) => setPlaybackTime(event.currentTarget.currentTime)}
                style={{ width: '100%', maxHeight: 430, display: 'block', background: '#000' }}
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
            <Empty description="选择视频后会立即在这里预览" />
          )}
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <Upload accept="video/*" showUploadList={false} beforeUpload={handleUpload} disabled={loading}>
              <Button icon={<UploadOutlined />} size="large" loading={loading}>
                选择视频文件
              </Button>
            </Upload>
            <div style={{ marginTop: 8, color: '#8c8c8c' }}>支持 MP4、AVI、MOV、WebM、MKV</div>
          </div>
          {loading && (
            <div style={{ margin: '18px auto 0', maxWidth: 420 }}>
              <Progress percent={progress} status="active" strokeColor="#1677ff" />
              <span style={{ color: '#8c8c8c' }}>正在提取关键点并进行时序分类，视频可先预览播放</span>
            </div>
          )}
        </Card>

        <Card title="视频识别结果">
          {result ? (
            <div style={{ textAlign: 'center' }}>
              <Tag color={GESTURE_COLORS[result.gestureId]} style={{ fontSize: 22, padding: '6px 20px', marginBottom: 12 }}>
                {getGestureLabel(result.gestureId, result.gesture)}
              </Tag>
              <Progress
                type="circle"
                percent={Math.round(result.confidence * 100)}
                size={88}
                strokeColor={GESTURE_COLORS[result.gestureId]}
              />
              <Descriptions size="small" column={1} style={{ marginTop: 12, textAlign: 'left' }}>
                <Descriptions.Item label="推理耗时">{inferenceMs.toFixed(0)} ms</Descriptions.Item>
                <Descriptions.Item label="分析帧数">{frames.length} 帧</Descriptions.Item>
                <Descriptions.Item label="视频帧率">{fps || '-'} fps</Descriptions.Item>
                <Descriptions.Item label="采样帧率">{sampleFps || '-'} fps</Descriptions.Item>
              </Descriptions>
              {top5.length > 0 && (
                <Space wrap style={{ marginTop: 8, justifyContent: 'center' }}>
                  {top5.map((item) => (
                    <Tag key={item.gestureId} color={GESTURE_COLORS[item.gestureId]}>
                      {getGestureLabel(item.gestureId, item.gesture)} {(item.confidence * 100).toFixed(0)}%
                    </Tag>
                  ))}
                </Space>
              )}
            </div>
          ) : (
            <Empty description={loading ? '等待后端返回识别结果' : '上传视频后显示识别结果'} />
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
                    background: GESTURE_COLORS[seg.gestureId],
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
                color={GESTURE_COLORS[seg.gestureId]}
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
            <div
              style={{
                position: 'absolute',
                left: 16,
                top: 16,
                padding: '8px 14px',
                borderRadius: 6,
                background: streamColor,
                color: '#fff',
                fontSize: 20,
                fontWeight: 700,
              }}
            >
              {streamLabel}
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
              <Tag color={streamColor} style={{ fontSize: 22, padding: '6px 20px', marginBottom: 16 }}>
                {streamLabel}
              </Tag>
              <Progress
                type="circle"
                percent={Math.round(streamResult.confidence * 100)}
                size={96}
                strokeColor={streamColor}
              />
              <Descriptions size="small" column={1} style={{ marginTop: 16, textAlign: 'left' }}>
                <Descriptions.Item label="推理耗时">{streamResult.inference_ms?.toFixed(0) || 0} ms</Descriptions.Item>
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
              <Tag key={`${item.timestamp}-${index}`} color={GESTURE_COLORS[item.gestureId]}>
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
