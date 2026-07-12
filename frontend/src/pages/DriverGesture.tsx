import React, { useState, useRef, useEffect } from 'react';
import { Card, Button, Space, Tag, Slider, Row, Col, Switch } from 'antd';
import { SoundOutlined, FireOutlined, StepForwardOutlined, StepBackwardOutlined, PlayCircleOutlined, PauseCircleOutlined, CameraOutlined, StopOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/common';
import { useAppStore } from '../store';
import { uploadDriverGestureImage } from '../api';
import request from '../api/request';

const HAND_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [0, 9], [9, 10], [10, 11], [11, 12],
  [0, 13], [13, 14], [14, 15], [15, 16],
  [0, 17], [17, 18], [18, 19], [19, 20],
  [5, 9], [9, 13], [13, 17]
];

// ===== ControlPanel 接收 playState =====
const ControlPanel: React.FC<{ playState: boolean }> = ({ playState }) => {
  const { volume, temperature, setVolume, setTemperature } = useAppStore();
  return (
    <Card title="车载中控面板" style={{ height: '100%' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div>
          <span><SoundOutlined style={{ marginRight: 8 }} />音量</span>
          <Tag color="blue">{volume}</Tag>
          <Slider value={volume} onChange={setVolume} />
        </div>
        <div>
          <span><FireOutlined style={{ marginRight: 8 }} />温度</span>
          {/* ✅ 温度显示向下取整 */}
          <Tag color="orange">{Math.floor(temperature)}°C</Tag>
          <Slider value={temperature} onChange={setTemperature} min={16} max={32} />
        </div>
        <div>
          <div style={{ marginBottom: 8, fontWeight: 500 }}>媒体控制</div>
          <Space size="middle">
            <Button shape="circle" icon={<StepBackwardOutlined />} size="large" />
            <Button
              shape="circle"
              icon={playState ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              size="large"
              type="primary"
            />
            <Button shape="circle" icon={<StepForwardOutlined />} size="large" />
          </Space>
        </div>
      </div>
    </Card>
  );
};

const DriverGesture: React.FC = () => {
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [streamActive, setStreamActive] = useState(false);
  const { setVolume, setTemperature } = useAppStore();

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [mirrorX, setMirrorX] = useState(true);

  const [playState, setPlayState] = useState(false);

  // ✅ 强制清空画布（独立函数，确保可靠）
  const clearCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  };

  const drawHand = (landmarks: number[][]) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const { width, height } = canvas;

    ctx.clearRect(0, 0, width, height);

    if (!landmarks || landmarks.length !== 21) {
      return; // 无数据，已清空
    }

    const pts = landmarks.map(([x, y]) => ({
      x: mirrorX ? width - x : x,
      y
    }));

    ctx.strokeStyle = '#00ff00';
    ctx.lineWidth = 2;
    for (const [i, j] of HAND_CONNECTIONS) {
      if (i < pts.length && j < pts.length) {
        ctx.beginPath();
        ctx.moveTo(pts[i].x, pts[i].y);
        ctx.lineTo(pts[j].x, pts[j].y);
        ctx.stroke();
      }
    }

    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4, 0, 2 * Math.PI);
      ctx.fillStyle = '#00ff00';
      ctx.fill();
    }
  };

  // 监听 canvas 尺寸变化，清空画布防止残留
  useEffect(() => {
    clearCanvas();
  }, [canvasSize]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const updateCanvasSize = () => {
      if (video.videoWidth && video.videoHeight) {
        setCanvasSize({ width: video.videoWidth, height: video.videoHeight });
      }
    };
    video.addEventListener('loadedmetadata', updateCanvasSize);
    video.addEventListener('resize', updateCanvasSize);
    return () => {
      video.removeEventListener('loadedmetadata', updateCanvasSize);
      video.removeEventListener('resize', updateCanvasSize);
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) {
      canvas.width = canvasSize.width;
      canvas.height = canvasSize.height;
    }
  }, [canvasSize]);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
      setStreamActive(true);
      await request.post('/driver-gesture/reset');

      const videoElement = videoRef.current;
      if (videoElement) {
        videoElement.srcObject = stream;
        videoElement.style.opacity = '1';
        await videoElement.play();
        setCanvasSize({
          width: videoElement.videoWidth,
          height: videoElement.videoHeight,
        });
      }

      let latestBlob: Blob | null = null;
      let processing = false;

      const captureInterval = setInterval(() => {
        const video = videoRef.current;
        if (!video || video.readyState < 2) return;
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx?.drawImage(video, 0, 0);
        canvas.toBlob((blob) => {
          if (blob) latestBlob = blob;
        }, 'image/jpeg', 0.8);
      }, 33);

      const processInterval = setInterval(async () => {
        if (processing || !latestBlob) return;
        processing = true;
        const blob = latestBlob;
        latestBlob = null;

        const file = new File([blob], 'frame.jpg', { type: 'image/jpeg' });
        try {
          const res = await uploadDriverGestureImage(file);
          if (res.data.code === 200 && res.data.data) {
            const result = res.data.data;
            const gestureName = result.gesture;
            const action = result.controlAction;
            const landmarks = result.landmarks;

            // ✅ 更新显示文本
            setLastAction(`${gestureName} → ${action?.label || gestureName}`);

            // ✅ 处理骨骼绘制：有数据时绘制，无数据时清空
            if (landmarks && landmarks.length === 21) {
              drawHand(landmarks);
            } else {
              clearCanvas(); // 强制清空
            }

            if (action) {
              switch (action.type) {
                case 'play_pause':
                  if (gestureName === '握拳') {
                    setPlayState(false);
                  } else if (gestureName === '手掌张开') {
                    setPlayState(true);
                  }
                  break;
                case 'volume_up': {
                  const currentVolume = useAppStore.getState().volume;
                  setVolume(Math.min(currentVolume + 2, 100));
                  break;
                }
                case 'volume_down': {
                  const currentVolume = useAppStore.getState().volume;
                  setVolume(Math.max(currentVolume - 2, 0));
                  break;
                }
                case 'temperature_up': {
                  const currentTemp = useAppStore.getState().temperature;
                  setTemperature(Math.min(currentTemp + 0.3, 32));
                  break;
                }
                case 'temperature_down': {
                  const currentTemp = useAppStore.getState().temperature;
                  setTemperature(Math.max(currentTemp - 0.3, 16));
                  break;
                }
                default:
                  break;
              }
            }
          }
        } catch (err) {
          console.warn('手势识别请求失败:', err);
        } finally {
          processing = false;
        }
      }, 200);

      (window as any).__captureInterval = captureInterval;
      (window as any).__processInterval = processInterval;

    } catch (err) {
      console.error('摄像头启动失败:', err);
      alert('无法访问摄像头，请检查权限设置');
    }
  };

  const stopCamera = () => {
    setStreamActive(false);
    clearInterval((window as any).__captureInterval);
    clearInterval((window as any).__processInterval);
    const video = videoRef.current;
    if (video && video.srcObject) {
      const tracks = (video.srcObject as MediaStream).getTracks();
      tracks.forEach(track => track.stop());
      video.srcObject = null;
      video.style.opacity = '0.3';
    }
    setLastAction(null);
    clearCanvas(); // 关闭时清空画布
  };

  return (
    <div>
      <PageHeader
        title="车主手势控车"
        subtitle="通过摄像头识别车主手势，实现隔空控制车载设备"
        extra={
          <Space>
            {streamActive ? (
              <Button icon={<StopOutlined />} danger onClick={stopCamera}>停止摄像头</Button>
            ) : (
              <Button icon={<CameraOutlined />} type="primary" onClick={startCamera}>开启摄像头</Button>
            )}
            <Switch
              checkedChildren="手部骨骼镜像"
              unCheckedChildren="手部骨骼镜像"
              checked={mirrorX}
              onChange={setMirrorX}
            />
          </Space>
        }
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="摄像头画面" style={{ minHeight: 400, position: 'relative' }}>
            <div style={{ width: '100%', height: 360, background: '#1a1a1a', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', overflow: 'hidden' }}>
              {streamActive ? (
                <>
                  <video ref={videoRef} autoPlay style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 8, opacity: 0.3 }} />
                  <canvas ref={canvasRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }} width={canvasSize.width} height={canvasSize.height} />
                  <div style={{ position: 'absolute', textAlign: 'center', color: '#fff' }}>
                    <CameraOutlined style={{ fontSize: 48, marginBottom: 12, display: 'block' }} />
                    <span>摄像头已开启</span>
                  </div>
                </>
              ) : (
                <div style={{ textAlign: 'center', color: '#666' }}>
                  <CameraOutlined style={{ fontSize: 64, marginBottom: 16 }} />
                  <p>点击"开启摄像头"开始手势识别</p>
                </div>
              )}
              {lastAction && (
                <div style={{ position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)', background: 'rgba(22,119,255,0.9)', color: '#fff', padding: '8px 24px', borderRadius: 20, fontSize: 16, fontWeight: 600 }}>
                  识别到: {lastAction}
                </div>
              )}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <ControlPanel playState={playState} />
        </Col>
      </Row>
    </div>
  );
};

export default DriverGesture;