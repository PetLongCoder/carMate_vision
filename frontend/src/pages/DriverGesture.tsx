import React, { useState } from 'react';
import { Card, Button, Space, Tag, Slider, Row, Col } from 'antd';
import { SoundOutlined, FireOutlined, StepForwardOutlined, StepBackwardOutlined, PlayCircleOutlined, PauseCircleOutlined, CameraOutlined, StopOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/common';
import { useAppStore } from '../store';

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

  const startCamera = () => {
    setStreamActive(true);
    const gestures = ['音量调高 ▲', '温度调低 ▼', '下一首 ⏭', '播放/暂停', '握拳确认 ✊'];
    let i = 0;
    const timer = setInterval(() => {
      const action = gestures[i % gestures.length];
      setLastAction(action);
      if (action.includes('音量调高')) setVolume(volume + 5);
      if (action.includes('温度调低')) setTemperature(temperature - 1);
      i++;
    }, 2000);
    (window as unknown as Record<string, number>).__gestureTimer = timer;
  };

  const stopCamera = () => {
    setStreamActive(false);
    clearInterval((window as unknown as Record<string, number>).__gestureTimer);
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
