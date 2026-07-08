import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Card, Input, Button, Space, Tag, Switch, message, Typography, Alert, Spin, Badge,
} from 'antd';
import {
  PlayCircleOutlined, StopOutlined, LinkOutlined, LoadingOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ExportOutlined,
} from '@ant-design/icons';
import { startStreamTracking, stopStreamTracking } from '../api';
import type { TrackedPlateResult, TrackedPlateSummary, WsPlateMessage, FrameDetection, TrackingSummary } from '../types';

const { Text } = Typography;

const PLATE_COLORS: Record<string, string> = {
  blue: '#1677ff', green: '#52c41a', yellow: '#faad14',
  white: '#d9d9d9', black: '#262626',
};

const VEHICLE_ICONS: Record<string, string> = {
  car: '🚗', bus: '🚌', truck: '🚛', motorcycle: '🏍️', unknown: '🚘',
};

function getColor(plateColor: string): string {
  return PLATE_COLORS[plateColor] || '#ff7a00';
}

const PlateStream: React.FC = () => {
  // ── 流连接 ──
  const [streamUrl, setStreamUrl] = useState('');
  const [streamName, setStreamName] = useState('');
  const [running, setRunning] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState(0);

  // ── 推流 ──
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushActive, setPushActive] = useState(false);
  const [pushAddress, setPushAddress] = useState<string | null>(null);

  // ── 检测结果 ──
  const [detections, setDetections] = useState<TrackedPlateResult[]>([]);
  const [summary, setSummary] = useState<TrackedPlateSummary[]>([]);
  const [summaryDone, setSummaryDone] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const detectionsRef = useRef<TrackedPlateResult[]>([]);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const lastValidRef = useRef<TrackedPlateResult[]>([]);

  // ── 画布绘制 ──
  const drawLoop = useCallback(() => {
    if (!canvasRef.current || !imgRef.current) { animRef.current = requestAnimationFrame(drawLoop); return; }
    const img = imgRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) { animRef.current = requestAnimationFrame(drawLoop); return; }

    const dpr = window.devicePixelRatio || 1;
    const rect = img.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, rect.width, rect.height);

    if (!img.naturalWidth || !img.naturalHeight) {
      animRef.current = requestAnimationFrame(drawLoop);
      return;
    }

    const current = detectionsRef.current;
    const drawTarget = current.length > 0 ? current : lastValidRef.current;
    const isStale = current.length === 0;

    if (drawTarget.length === 0) {
      animRef.current = requestAnimationFrame(drawLoop);
      return;
    }

    if (!isStale) lastValidRef.current = current;

    const sx = rect.width / img.naturalWidth;
    const sy = rect.height / img.naturalHeight;

    if (isStale) ctx.globalAlpha = 0.35;

    for (const d of drawTarget) {
      const x = d.bbox.x * sx;
      const y = d.bbox.y * sy;
      const w = d.bbox.width * sx;
      const h = d.bbox.height * sy;
      const color = getColor(d.color);

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

      const info = `${d.color} · ${(d.confidence * 100).toFixed(0)}%`;
      ctx.font = '11px -apple-system, sans-serif';
      ctx.fillStyle = color;
      ctx.fillText(info, x, y > 30 ? y - 36 : y + h + 36);
    }

    if (isStale) ctx.globalAlpha = 1.0;
    animRef.current = requestAnimationFrame(drawLoop);
  }, []);

  useEffect(() => {
    animRef.current = requestAnimationFrame(drawLoop);
    return () => cancelAnimationFrame(animRef.current);
  }, [drawLoop]);

  // ── WebSocket ──
  const connectWs = useCallback((sid: string) => {
    const base = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
    const ws = new WebSocket(`${base}/api/ws/plate/track/${sid}`);
    wsRef.current = ws;
    ws.onopen = () => { message.success('已连接实时追踪'); };
    ws.onmessage = (ev) => {
      try {
        const msg: WsPlateMessage = JSON.parse(ev.data);
        switch (msg.type) {
          case 'detection': {
            const det = msg as FrameDetection;
            detectionsRef.current = det.detections;
            setDetections(det.detections);
            setFrameCount(n => n + 1);
            break;
          }
          case 'summary': {
            const sm = msg as TrackingSummary;
            setSummary(sm.plates);
            setSummaryDone(true);
            message.success(`追踪完成! 共识别 ${sm.plates.length} 个车牌`);
            break;
          }
          case 'error': message.error(msg.message); break;
        }
      } catch { /* ignore */ }
    };
    ws.onerror = () => message.warning('WebSocket 连接失败');
    ws.onclose = () => {
      wsRef.current = null;
      setRunning(false);
      setConnecting(false);
    };
  }, []);

  // ── 启动 ──
  const handleStart = async () => {
    if (!streamUrl.trim()) { message.warning('请输入流地址'); return; }
    setConnecting(true);
    setSummary([]);
    setSummaryDone(false);
    setFrameCount(0);
    lastValidRef.current = [];
    detectionsRef.current = [];
    setDetections([]);
    try {
      const res = await startStreamTracking(
        streamUrl.trim(), streamName.trim() || undefined,
        pushEnabled || undefined, undefined,
      );
      if (res.data.code === 200) {
        const { sessionId: sid, pushEnabled: pe, pushUrl: pu } = res.data.data;
        setSessionId(sid);
        setPushActive(!!pe);
        setPushAddress(pu);
        setRunning(true);
        setConnecting(false);
        connectWs(sid);
      } else {
        message.error(res.data.message || '启动失败');
        setConnecting(false);
      }
    } catch {
      message.error('无法连接后端服务');
      setConnecting(false);
    }
  };

  // ── 停止 ──
  const handleStop = async () => {
    if (sessionId) try { await stopStreamTracking(sessionId); } catch { /* ignore */ }
    if (wsRef.current) wsRef.current.close();
    setRunning(false);
    setSessionId(null);
    setPushActive(false);
    message.info('已停止');
  };

  // ── 清理 ──
  useEffect(() => () => { if (wsRef.current) wsRef.current.close(); }, []);

  const mjpegUrl = sessionId ? `/api/plate/stream/${sessionId}/mjpeg` : '';

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <Card style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 280 }}>
            <Text strong style={{ fontSize: 15 }}>摄像头流地址</Text>
            <Input
              placeholder="rtsp://10.126.59.120:8554/live/live1"
              prefix={<LinkOutlined />}
              value={streamUrl}
              onChange={e => setStreamUrl(e.target.value)}
              size="large"
              disabled={running || connecting}
            />
          </div>
          <div style={{ minWidth: 140 }}>
            <Text strong style={{ fontSize: 15 }}>名称（可选）</Text>
            <Input
              placeholder="桥面摄像头"
              value={streamName}
              onChange={e => setStreamName(e.target.value)}
              size="large"
              disabled={running || connecting}
            />
          </div>
          <Button
            type="primary"
            icon={running ? <StopOutlined /> : <PlayCircleOutlined />}
            size="large"
            onClick={running ? handleStop : handleStart}
            danger={running}
            loading={connecting}
            style={{ minWidth: 130, height: 40 }}
          >
            {connecting ? '连接中...' : running ? '停止' : '启动识别'}
          </Button>
        </div>

        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <Switch
            checked={pushEnabled}
            onChange={setPushEnabled}
            disabled={running || connecting}
            checkedChildren="推流开"
            unCheckedChildren="推流关"
          />
          <Text type="secondary">将识别画面推送到 MediaMTX（HLS/WebRTC 查看）</Text>
        </div>
      </Card>

      {/* 运行状态 */}
      {running && (
        <Card size="small" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
            <Space>
              <Badge status="processing" color="green" />
              <Text strong>实时追踪中</Text>
              <Text code style={{ fontSize: 12 }}>{sessionId}</Text>
            </Space>
            <Space size={16}>
              <Text type="secondary">已处理 <Text strong>{frameCount}</Text> 帧</Text>
              <Badge status="success" text={<Text style={{ fontSize: 13 }}>已连接</Text>} />
            </Space>
          </div>
          {pushActive && pushAddress && (
            <div style={{ marginTop: 8, padding: '8px 12px', background: '#f6ffed', borderRadius: 6, fontSize: 13 }}>
              <Tag color="success" icon={<ExportOutlined />}>推流中</Tag>
              <Text code>{pushAddress}</Text>
              <Text type="secondary" style={{ marginLeft: 12 }}>
                HLS: <Text code>http://localhost:8888/recognized/{sessionId}/index.m3u8</Text>
              </Text>
            </div>
          )}
        </Card>
      )}

      {/* 视频 + 结果 */}
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
        <Card
          title="实时视频"
          style={{ flex: '1 1 600px' }}
          extra={running ? <Badge status="processing" text={`${frameCount} 帧`} /> : null}
        >
          {running && mjpegUrl ? (
            <div style={{ position: 'relative', background: '#000', borderRadius: 8, minHeight: 300 }}>
              <img
                ref={imgRef}
                src={mjpegUrl}
                alt="stream"
                style={{ maxWidth: '100%', maxHeight: 500, borderRadius: 8, display: 'block' }}
              />
              <canvas
                ref={canvasRef}
                style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', borderRadius: 8 }}
              />
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '80px 0', color: '#999' }}>
              <LinkOutlined style={{ fontSize: 48, marginBottom: 16 }} />
              <div>输入流地址并启动识别</div>
            </div>
          )}
        </Card>

        {/* 检测结果面板 */}
        <div style={{ flex: '1 1 300px', minWidth: 280 }}>
          <Card title={`当前检测 (${detections.length} 个)`}>
            {detections.length > 0 ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                {detections.map(d => (
                  <div key={d.trackId} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '8px 12px', background: '#f6f8fa', borderRadius: 6,
                    borderLeft: `4px solid ${getColor(d.color)}`,
                  }}>
                    <Space>
                      <Text strong style={{ fontSize: 16 }}>{d.plateNo}</Text>
                      <Tag color={d.color === 'green' ? 'green' : d.color === 'yellow' ? 'orange' : 'blue'}>
                        {d.color}牌
                      </Tag>
                      <Text type="secondary">{VEHICLE_ICONS[d.vehicleType] || ''} {d.vehicleType}</Text>
                    </Space>
                    <Text type="secondary">{(d.confidence * 100).toFixed(0)}%</Text>
                  </div>
                ))}
              </Space>
            ) : (
              <div style={{ textAlign: 'center', padding: 40 }}>
                {running ? (
                  <><Spin indicator={<LoadingOutlined style={{ fontSize: 24 }} />} /><div style={{ marginTop: 12 }}>等待检测结果...</div></>
                ) : (
                  <Text type="secondary">暂无数据</Text>
                )}
              </div>
            )}
          </Card>

          {/* 汇总 */}
          {summary.length > 0 && (
            <Card title={`识别汇总 (${summary.length} 个车牌)`} style={{ marginTop: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                {summary.map(p => (
                  <div key={p.trackId} style={{
                    display: 'flex', justifyContent: 'space-between',
                    padding: '6px 8px', background: '#fafafa', borderRadius: 4,
                  }}>
                    <Space>
                      <Text strong>{p.plateNo}</Text>
                      <Tag color="blue">{p.color}牌</Tag>
                    </Space>
                    <Text type="secondary">{(p.confidence * 100).toFixed(0)}% · {p.appearances}次</Text>
                  </div>
                ))}
              </Space>
            </Card>
          )}
        </div>
      </div>

      {!running && !connecting && (
        <Card style={{ marginTop: 20 }}>
          <Alert
            type="info"
            showIcon
            message="使用说明"
            description={
              <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 2 }}>
                <li>确保 <Text code>mediamtx.exe</Text> 和 FFmpeg 已启动</li>
                <li>在上方输入摄像头 RTSP 流地址（沙盘: <Text code>rtsp://10.126.59.120:8554/live/live1</Text> ~ live12）</li>
                <li>若需要本地测试：<Text code>ffmpeg -re -i test.mp4 -f rtsp rtsp://localhost:8554/camera</Text></li>
                <li>点击 <Tag color="blue">启动识别</Tag>，实时画面将显示检测框和车牌号</li>
                <li>开启推流后可在浏览器查看 HLS/WebRTC 识别画面</li>
              </ol>
            }
          />
        </Card>
      )}
    </div>
  );
};

export default PlateStream;
