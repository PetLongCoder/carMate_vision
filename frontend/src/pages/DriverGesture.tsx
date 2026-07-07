import React, { useState } from 'react';
import { Card, Button, Space, Tag, Slider, Row, Col } from 'antd';
import { SoundOutlined, FireOutlined, StepForwardOutlined, StepBackwardOutlined, PlayCircleOutlined, PauseCircleOutlined, CameraOutlined, StopOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/common';
import { useAppStore } from '../store';
import { uploadDriverGestureImage } from '../api';

const ControlPanel: React.FC = () => {
  const { volume, temperature, setVolume, setTemperature } = useAppStore();

  return (
    <Card title="车载中控面板" style={{ height: '100%' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span><SoundOutlined style={{ marginRight: 8 }} />音量</span>
            <Tag color="blue">{volume}</Tag>
          </div>
          <Slider value={volume} onChange={setVolume} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span><FireOutlined style={{ marginRight: 8 }} />温度</span>
            <Tag color="orange">{temperature}°C</Tag>
          </div>
          <Slider value={temperature} onChange={setTemperature} min={16} max={32} />
        </div>
        <div>
          <div style={{ marginBottom: 8, fontWeight: 500 }}>媒体控制</div>
          <Space size="middle">
            <Button shape="circle" icon={<StepBackwardOutlined />} size="large" />
            <Button shape="circle" icon={<PlayCircleOutlined />} size="large" type="primary" />
            <Button shape="circle" icon={<PauseCircleOutlined />} size="large" />
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
  const { setVolume, setTemperature, volume, temperature } = useAppStore();

const startCamera = async () => {
  try {
    // 1. 获取摄像头视频流
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
    setStreamActive(true);

    // 找到页面中的 video 元素，显示视频流
    const videoElement = document.querySelector('video') as HTMLVideoElement;
    if (videoElement) {
      videoElement.srcObject = stream;
      videoElement.style.opacity = '1'; // 取消半透明
      await videoElement.play();
    }

    // 2. 每隔 500ms 捕获一帧发送给后端
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    const timer = setInterval(async () => {
      const video = document.querySelector('video') as HTMLVideoElement;
      if (!video || video.readyState < 2) return;

      // 从视频中截取一帧
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx?.drawImage(video, 0, 0);
      
      // 将 canvas 转为 Blob (JPEG 格式)
      const blob = await new Promise<Blob | null>((resolve) => {
        canvas.toBlob(resolve, 'image/jpeg', 0.8);
      });
      if (!blob) return;

      // 构造 File 对象，调用后端接口
      const file = new File([blob], 'frame.jpg', { type: 'image/jpeg' });
      try {
        const res = await uploadDriverGestureImage(file);
        if (res.data.code === 200 && res.data.data) {
          const result = res.data.data;
          const gestureName = result.gesture;          // 如 "握拳"
          const action = result.controlAction;         // 如 { type: "play_pause", label: "播放/暂停" }

          // 更新界面显示
          setLastAction(`${gestureName} → ${action?.label || gestureName}`);

          // 根据 controlAction.type 同步更新控件
          if (action) {
            switch (action.type) {
              case 'volume_up':
                setVolume(Math.min(volume + 5, 100));
                break;
              case 'volume_down':
                setVolume(Math.max(volume - 5, 0));
                break;
              case 'temperature_up':
                setTemperature(Math.min(temperature + 1, 32));
                break;
              case 'temperature_down':
                setTemperature(Math.max(temperature - 1, 16));
                break;
              case 'next_track':
                // 你可以在这里触发 UI 反馈，比如高亮按钮
                break;
              case 'prev_track':
                break;
              case 'play_pause':
                // 切换播放/暂停状态
                break;
              default:
                break;
            }
          }
        }
      } catch (err) {
        console.warn('手势识别请求失败:', err);
      }
    }, 500); // 每 500ms 识别一次（抽帧节流）

    // 保存 timer，供 stopCamera 清除
    (window as any).__gestureTimer = timer;

  } catch (err) {
    console.error('摄像头启动失败:', err);
    alert('无法访问摄像头，请检查权限设置');
  }
};

const stopCamera = () => {
  setStreamActive(false);
  // 清除定时器
  clearInterval((window as any).__gestureTimer);
  // 停止视频流
  const video = document.querySelector('video') as HTMLVideoElement;
  if (video && video.srcObject) {
    const tracks = (video.srcObject as MediaStream).getTracks();
    tracks.forEach(track => track.stop());
    video.srcObject = null;
    video.style.opacity = '0.3';
  }
  setLastAction(null);
};

  return (
    <div>
      <PageHeader title="车主手势控车" subtitle="通过摄像头识别车主手势，实现隔空控制车载设备"
        extra={
          <Space>
            {streamActive ? (
              <Button icon={<StopOutlined />} danger onClick={stopCamera}>停止摄像头</Button>
            ) : (
              <Button icon={<CameraOutlined />} type="primary" onClick={startCamera}>开启摄像头</Button>
            )}
          </Space>
        } />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="摄像头画面" style={{ minHeight: 400 }}>
            <div style={{ width: '100%', height: 360, background: '#1a1a1a', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
              {streamActive ? (
                <>
                  <video autoPlay style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 8, opacity: 0.3 }} />
                  <div style={{ position: 'absolute', textAlign: 'center', color: '#fff' }}>
                    <CameraOutlined style={{ fontSize: 48, marginBottom: 12, display: 'block' }} />
                    <span>摄像头已开启 (模拟)</span>
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
        <Col xs={24} lg={10}><ControlPanel /></Col>
      </Row>
    </div>
  );
};

export default DriverGesture;
