import React, { useState, useRef } from 'react';
import { Card, Upload, Button, Space, Tag, Progress, message, Descriptions, Empty } from 'antd';
import { UploadOutlined, PlayCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/common';
import type { PoliceGestureResult } from '../types';
import { uploadPoliceGestureVideo } from '../api';

const GESTURE_COLORS: Record<string, string> = {
  '停止': '#f5222d', '直行': '#1677ff', '左转': '#722ed1', '右转': '#fa8c16',
  '左转待转': '#eb2f96', '变道': '#52c41a', '减速慢行': '#faad14', '靠边停车': '#13c2c2',
  '无手势': '#d9d9d9',
};

type FrameResult = { frame: number; time: number; gesture: string; gestureId: number; confidence: number };
type Segment = { start: number; end: number; gesture: string; gestureId: number };

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
  const videoRef = useRef<HTMLVideoElement>(null);

  const handleUpload = async (file: File) => {
    setLoading(true);
    setProgress(0);
    setResult(null);
    setFrames([]);
    setSegments([]);

    const progressTimer = setInterval(() => setProgress((p) => {
      if (p >= 90) { clearInterval(progressTimer); return 90; }
      return p + 3;
    }), 200);

    // 预览视频
    const reader = new FileReader();
    reader.onload = (e) => setVideoSrc(e.target?.result as string);
    reader.readAsDataURL(file);

    try {
      const response = await uploadPoliceGestureVideo(file);
      const data = (response.data as any).data || response.data;

      clearInterval(progressTimer);
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
      setDuration(data.video_duration || 0);
      setFps(data.video_fps || 0);
      message.success(`识别完成: ${data.gesture} | ${data.segments?.length || 0} 个手势段`);
    } catch (error) {
      clearInterval(progressTimer);
      setProgress(0);
      console.error('手势识别失败:', error);
      message.error('识别失败，请确认后端服务已启动');
    }

    setLoading(false);
    return false;
  };

  // 跳到指定时间
  const seekTo = (seconds: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      videoRef.current.play();
    }
  };

  return (
    <div>
      <PageHeader title="交警手势识别" subtitle="上传交警手势视频，自动识别8种交通指挥手势并标注时间线"
        extra={<Space><Button icon={<PlayCircleOutlined />} type="primary">实时摄像头</Button></Space>} />

      <Card style={{ marginBottom: 24, textAlign: 'center' }}>
        <Upload accept="video/*" showUploadList={false} beforeUpload={handleUpload} disabled={loading}>
          <Button icon={<UploadOutlined />} size="large" loading={loading}>选择视频文件</Button>
        </Upload>
        <p style={{ marginTop: 12, color: '#999' }}>支持 MP4、AVI、MOV 格式</p>
        {loading && (
          <div style={{ margin: '24px auto', maxWidth: 400 }}>
            <Progress percent={progress} status="active" strokeColor="#1677ff" />
            <span style={{ color: '#999' }}>正在逐帧分析手势...</span>
          </div>
        )}
      </Card>

      {result && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          {/* 视频区域 */}
          <Card title="视频预览" style={{ flex: '1 1 500px', minWidth: 350 }}
            extra={duration > 0 && <Tag color="blue">{duration.toFixed(0)}秒 | {segments.length} 段手势</Tag>}>
            {videoSrc ? (
              <div>
                <video ref={videoRef} src={videoSrc} controls
                  style={{ width: '100%', maxHeight: 360, borderRadius: 8, background: '#000' }} />
              </div>
            ) : <p>加载中...</p>}
          </Card>

          {/* 结果概览 */}
          <Card title="识别结果" style={{ flex: '1 1 300px', minWidth: 280 }}>
            <div style={{ textAlign: 'center', padding: '10px 0' }}>
              <Tag color="purple" style={{ fontSize: 22, padding: '6px 20px', marginBottom: 12 }}>
                {result.gesture}
              </Tag>
              <Progress type="circle" percent={Math.round(result.confidence * 100)} size={80}
                strokeColor={result.confidence > 0.8 ? '#52c41a' : result.confidence > 0.5 ? '#faad14' : '#ff4d4f'} />
              <p style={{ color: '#999', marginTop: 8 }}>综合置信度</p>

              <Descriptions size="small" column={1} style={{ marginTop: 12, textAlign: 'left' }}>
                <Descriptions.Item label="推理耗时">{inferenceMs.toFixed(0)} ms</Descriptions.Item>
                <Descriptions.Item label="分析帧数">{frames.length} 帧</Descriptions.Item>
                <Descriptions.Item label="视频帧率">{fps} fps</Descriptions.Item>
              </Descriptions>

              {top5.length > 1 && (
                <div style={{ marginTop: 12, textAlign: 'left' }}>
                  <p style={{ fontWeight: 500, marginBottom: 6 }}>手势分布:</p>
                  {top5.map((t, i) => (
                    <Tag key={i} color={i === 0 ? 'purple' : 'default'} style={{ marginBottom: 4 }}>
                      {t.gesture}: {(t.confidence * 100).toFixed(0)}%
                    </Tag>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* 手势时间线 */}
      {segments.length > 0 && (
        <Card title="手势时间线" style={{ marginTop: 24 }}
          extra={<span style={{ color: '#999', fontSize: 13 }}>
            <ClockCircleOutlined /> 点击时间段可跳转视频
          </span>}>
          <div style={{ position: 'relative', height: 60, background: '#f5f5f5', borderRadius: 8, overflow: 'hidden', marginBottom: 16 }}>
            {segments.map((seg, i) => {
              const left = (seg.start / duration) * 100;
              const width = Math.max(((seg.end - seg.start) / duration) * 100, 1);
              return (
                <div key={i}
                  onClick={() => seekTo(seg.start)}
                  title={`${seg.start.toFixed(1)}s - ${seg.end.toFixed(1)}s: ${seg.gesture}`}
                  style={{
                    position: 'absolute', left: `${left}%`, width: `${width}%`,
                    height: '100%', cursor: 'pointer',
                    background: GESTURE_COLORS[seg.gesture] || '#d9d9d9',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#fff', fontWeight: 600, fontSize: 13,
                    borderRight: '2px solid #fff',
                    transition: 'opacity 0.2s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.opacity = '0.8')}
                  onMouseLeave={(e) => (e.currentTarget.style.opacity = '1')}
                >
                  {width > 8 ? seg.gesture : ''}
                </div>
              );
            })}
          </div>

          {/* 时间轴刻度 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#999', marginBottom: 16 }}>
            <span>0s</span>
            <span>{(duration / 4).toFixed(0)}s</span>
            <span>{(duration / 2).toFixed(0)}s</span>
            <span>{(duration * 3 / 4).toFixed(0)}s</span>
            <span>{duration.toFixed(0)}s</span>
          </div>

          {/* 手势图例和分段列表 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            {segments.map((seg, i) => (
              <Tag key={i} color={GESTURE_COLORS[seg.gesture]}
                style={{ cursor: 'pointer', padding: '4px 12px', fontSize: 13 }}
                onClick={() => seekTo(seg.start)}>
                {seg.gesture}: {seg.start.toFixed(1)}s - {seg.end.toFixed(1)}s
              </Tag>
            ))}
          </div>
        </Card>
      )}

      {/* 逐帧列表 */}
      {frames.length > 0 && (
        <Card title={`逐帧分析 (${frames.length} 帧)`} style={{ marginTop: 16 }}>
          <div style={{ maxHeight: 300, overflow: 'auto' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {frames.map((f, i) => (
                <Tag key={i}
                  color={f.gestureId > 0 ? (GESTURE_COLORS[f.gesture] || 'default') : 'default'}
                  style={{ cursor: 'pointer' }}
                  onClick={() => seekTo(f.time)}
                  title={`${f.time.toFixed(2)}s: ${f.gesture} (${(f.confidence * 100).toFixed(0)}%)`}>
                  {f.time.toFixed(1)}s {f.gesture}
                </Tag>
              ))}
            </div>
          </div>
        </Card>
      )}

      {!result && !loading && (
        <Card><Empty description="请上传交警手势视频开始识别" /></Card>
      )}
    </div>
  );
};

export default PoliceGesture;
