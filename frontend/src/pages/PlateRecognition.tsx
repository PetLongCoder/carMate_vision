import React, { useState } from 'react';
import { Card, Upload, Button, Space, Tag, Table, message } from 'antd';
import { CameraOutlined, InboxOutlined, CarOutlined } from '@ant-design/icons';
import { PageHeader, Empty } from '../components/common';
import { uploadPlateImage } from '../api';
import type { PlateResult } from '../types';

const { Dragger } = Upload;

const VEHICLE_TYPE_MAP: Record<string, { label: string; color: string; icon: string }> = {
  car: { label: '轿车', color: 'blue', icon: '🚗' },
  bus: { label: '客车', color: 'purple', icon: '🚌' },
  truck: { label: '卡车', color: 'orange', icon: '🚛' },
  motorcycle: { label: '摩托车', color: 'cyan', icon: '🏍️' },
  unknown: { label: '未知', color: 'default', icon: '🚘' },
};

const columns = [
  { title: '车辆编号', dataIndex: 'carId', key: 'carId', width: 90 },
  { title: '车型', dataIndex: 'vehicleType', key: 'vehicleType', width: 100,
    render: (t: string) => {
      const info = VEHICLE_TYPE_MAP[t] || VEHICLE_TYPE_MAP.unknown;
      return <Tag color={info.color}>{info.icon} {info.label}</Tag>;
    },
  },
  { title: '车牌号码', dataIndex: 'plateNo', key: 'plateNo',
    render: (text: string) => <Tag color="blue" style={{ fontSize: 16, fontWeight: 600 }}>{text}</Tag> },
  { title: '颜色', dataIndex: 'color', key: 'color',
    render: (c: string) => <Tag color={c === 'blue' ? 'blue' : c === 'green' ? 'green' : 'orange'}>{c}</Tag> },
  { title: '置信度', dataIndex: 'confidence', key: 'confidence',
    render: (v: number) => `${(v * 100).toFixed(1)}%` },
];

const PlateRecognition: React.FC = () => {
  const [results, setResults] = useState<PlateResult[]>([]);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [imageScale, setImageScale] = useState<{ x: number; y: number }>({ x: 1, y: 1 });

  const handleUpload = async (file: File) => {
    setLoading(true);
    setResults([]);
    setImageScale({ x: 1, y: 1 });

    // 先显示图片预览
    const reader = new FileReader();
    reader.onload = (e) => setPreviewImage(e.target?.result as string);
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
      message.error('请求失败，请检查后端服务是否已启动');
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

  return (
    <div>
      <PageHeader title="车牌识别" subtitle="上传道路图片或视频流，自动检测并识别车牌信息"
        extra={<Space><Button icon={<CameraOutlined />} type="primary">开启摄像头</Button></Space>} />

      <Card style={{ marginBottom: 24 }}>
        <Dragger accept="image/*,video/*" showUploadList={false} beforeUpload={handleUpload} disabled={loading}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽图片/视频到此处上传</p>
          <p className="ant-upload-hint">支持 JPG、PNG、MP4 格式</p>
        </Dragger>
      </Card>

      {previewImage && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <Card title="图片预览" style={{ flex: '1 1 400px' }}>
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <img src={previewImage} alt="preview" style={{ maxWidth: '100%', maxHeight: 400, borderRadius: 8 }} onLoad={handleImageLoad} />
              {results.map((r) => (
                <div key={r.carId} style={{ position: 'absolute', left: r.bbox.x * imageScale.x, top: r.bbox.y * imageScale.y, width: r.bbox.width * imageScale.x, height: r.bbox.height * imageScale.y, border: '2px solid #1677ff', borderRadius: 4, pointerEvents: 'none' }}>
                  <span style={{ position: 'absolute', top: -24, left: 0, background: '#1677ff', color: '#fff', padding: '2px 8px', borderRadius: 4, fontSize: 12, whiteSpace: 'nowrap' }}>{r.plateNo} · {VEHICLE_TYPE_MAP[r.vehicleType]?.label || r.vehicleType}</span>
                </div>
              ))}
            </div>
          </Card>
          <Card title="识别结果" style={{ flex: '1 1 300px', minWidth: 300 }}>
            {results.length > 0 ? <Table columns={columns} dataSource={results} rowKey="carId" pagination={false} size="small" /> : <Empty description="未识别到车牌" />}
          </Card>
        </div>
      )}

      {!previewImage && <Card><Empty description="请先上传图片开始识别" /></Card>}
    </div>
  );
};

export default PlateRecognition;
