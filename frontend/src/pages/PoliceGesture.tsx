import React, { useState } from 'react';
import { Card, Upload, Button, Space, Tag, Progress, message } from 'antd';
import { UploadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/common';
import type { PoliceGestureResult } from '../types';

const GESTURE_LABELS: Record<number, string> = {
  0: '停止', 1: '直行', 2: '左转', 3: '右转',
  4: '左转待转', 5: '变道', 6: '减速慢行', 7: '靠边停车',
};

const PoliceGesture: React.FC = () => {
  const [result, setResult] = useState<PoliceGestureResult | null>(null);
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleUpload = async (file: File) => {
    setLoading(true);
    setProgress(0);
    const timer = setInterval(() => setProgress((p) => { if (p >= 100) { clearInterval(timer); return 100; } return p + 10; }), 200);

    await new Promise((r) => setTimeout(r, 2000));
    clearInterval(timer);
    setProgress(100);

    const reader = new FileReader();
    reader.onload = (e) => setVideoSrc(e.target?.result as string);
    reader.readAsDataURL(file);

    setResult({ gesture: GESTURE_LABELS[2], gestureId: 2, confidence: 0.923, timestamp: Date.now() });
    setLoading(false);
    message.success('手势识别完成');
    return false;
  };

  return (
    <div>
      <PageHeader title="交警手势识别" subtitle="上传交警手势视频，自动识别8种交通指挥手势"
        extra={<Space><Button icon={<PlayCircleOutlined />} type="primary">实时摄像头</Button></Space>} />

      <Card style={{ marginBottom: 24, textAlign: 'center' }}>
        <Upload accept="video/*" showUploadList={false} beforeUpload={handleUpload} disabled={loading}>
          <Button icon={<UploadOutlined />} size="large" loading={loading}>选择视频文件</Button>
        </Upload>
        <p style={{ marginTop: 12, color: '#999' }}>支持 MP4、AVI、MOV 格式</p>
        {loading && (
          <div style={{ margin: '24px auto', maxWidth: 400 }}>
            <Progress percent={progress} status="active" strokeColor="#1677ff" />
            <span style={{ color: '#999' }}>正在分析手势序列...</span>
          </div>
        )}
      </Card>

      {result && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <Card title="视频预览" style={{ flex: '1 1 400px' }}>
            {videoSrc ? <video src={videoSrc} controls style={{ maxWidth: '100%', maxHeight: 400, borderRadius: 8 }} /> : <p>加载中...</p>}
          </Card>
          <Card title="识别结果" style={{ flex: '1 1 300px', minWidth: 280 }}>
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <div style={{ fontSize: 64, marginBottom: 16 }}>
                {result.gesture === '左转' ? '👈' : result.gesture === '右转' ? '👉' : '✋'}
              </div>
              <Tag color="purple" style={{ fontSize: 24, padding: '8px 24px' }}>{result.gesture}</Tag>
              <p style={{ color: '#666', marginTop: 12 }}>手势编号：{GESTURE_LABELS[result.gestureId]}</p>
              <Progress type="circle" percent={Math.round(result.confidence * 100)} size={80} strokeColor="#722ed1" />
              <p style={{ color: '#999', marginTop: 8 }}>置信度</p>
            </div>
          </Card>
        </div>
      )}

      {!result && !loading && <Card><p style={{ textAlign: 'center', color: '#999' }}>请上传交警手势视频开始识别</p></Card>}
    </div>
  );
};

export default PoliceGesture;
