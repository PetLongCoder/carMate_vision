import React, { useState } from 'react';
import { Card, Table, Tag, Space, Button, Modal, Typography, Segmented } from 'antd';
import { CheckCircleOutlined, ExclamationCircleOutlined, BellOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/common';
import type { Alert, AlertLevel } from '../types';
import dayjs from 'dayjs';

const levelConfig: Record<AlertLevel, { color: string; icon: React.ReactNode; label: string }> = {
  info: { color: 'blue', icon: <BellOutlined />, label: '提示' },
  warning: { color: 'orange', icon: <ExclamationCircleOutlined />, label: '警告' },
  critical: { color: 'red', icon: <ExclamationCircleOutlined />, label: '严重' },
};

const mockAlerts: Alert[] = [
  { id: 1, level: 'warning', title: '车牌识别失败率升高', summary: '最近5分钟内车牌识别失败率达到30%，请检查摄像头角度和光照条件。建议清洁镜头并确保光线充足。', source: '车牌识别模块', createdAt: dayjs().subtract(5, 'minute').toISOString(), acknowledged: false },
  { id: 2, level: 'info', title: '系统启动完成', summary: 'CarMate 智能车载视觉系统已成功启动，所有模块运行正常。当前CPU使用率12%，内存使用率48%。', source: '系统', createdAt: dayjs().subtract(30, 'minute').toISOString(), acknowledged: true },
  { id: 3, level: 'critical', title: '手势识别模块离线', summary: '车主手势识别模块无响应超过60秒，已尝试自动重启。请检查MediaPipe服务是否正常运行。', source: '手势识别模块', createdAt: dayjs().subtract(1, 'hour').toISOString(), acknowledged: false },
  { id: 4, level: 'warning', title: 'GPU显存使用率过高', summary: 'GPU显存使用率达到85%，可能影响视频流处理性能。建议降低并发处理帧数或考虑模型量化。', source: 'AI服务', createdAt: dayjs().subtract(2, 'hour').toISOString(), acknowledged: false },
  { id: 5, level: 'info', title: '数据库备份完成', summary: '今日数据库定时备份已完成，备份大小23MB，耗时3.2秒。备份文件已存储至 /backups/2026-07-06/。', source: '数据库', createdAt: dayjs().subtract(3, 'hour').toISOString(), acknowledged: true },
];

const AlertCenter: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>(mockAlerts);
  const [filter, setFilter] = useState<string>('all');
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);

  const filtered = filter === 'all' ? alerts : alerts.filter((a) => a.level === filter);

  const columns = [
    { title: '级别', dataIndex: 'level', key: 'level', width: 80,
      render: (level: AlertLevel) => { const cfg = levelConfig[level]; return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>; } },
    { title: '标题', dataIndex: 'title', key: 'title', width: 200 },
    { title: '来源', dataIndex: 'source', key: 'source', width: 120 },
    { title: '时间', dataIndex: 'createdAt', key: 'createdAt', width: 160,
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss') },
    { title: '状态', dataIndex: 'acknowledged', key: 'acknowledged', width: 80,
      render: (ack: boolean) => ack ? <Tag color="default">已确认</Tag> : <Tag color="processing">未确认</Tag> },
  ];

  return (
    <div>
      <PageHeader title="告警中心" subtitle="实时接收系统告警，查看告警摘要和详情"
        extra={
          <Button type="primary" danger icon={<BellOutlined />} onClick={() => {
            const newAlert: Alert = { id: Date.now(), level: 'warning', title: '模拟告警', summary: '这是一条模拟告警，用于测试告警中心和WebSocket推送功能。', source: '测试', createdAt: new Date().toISOString(), acknowledged: false };
            setAlerts((prev) => [newAlert, ...prev]);
          }}>模拟告警</Button>
        } />

      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Segmented options={[
            { label: '全部', value: 'all' }, { label: '提示', value: 'info' },
            { label: '警告', value: 'warning' }, { label: '严重', value: 'critical' },
          ]} value={filter} onChange={(v) => setFilter(v as string)} />
        </Space>

        <Table columns={columns} dataSource={filtered} rowKey="id" pagination={{ pageSize: 10 }}
          onRow={(record) => ({ onClick: () => setSelectedAlert(record),
            style: { cursor: 'pointer', fontWeight: record.acknowledged ? 'normal' : 600 } })} />
      </Card>

      <Modal title={selectedAlert?.title} open={!!selectedAlert} onCancel={() => setSelectedAlert(null)}
        footer={[
          <Button key="close" onClick={() => setSelectedAlert(null)}>关闭</Button>,
          <Button key="ack" type="primary" icon={<CheckCircleOutlined />} onClick={() => {
            if (selectedAlert) { setAlerts((prev) => prev.map((a) => (a.id === selectedAlert.id ? { ...a, acknowledged: true } : a))); setSelectedAlert(null); }
          }}>确认告警</Button>,
        ]} width={600}>
        {selectedAlert && (
          <div>
            <Space style={{ marginBottom: 16 }}>
              <Tag color={levelConfig[selectedAlert.level].color}>{levelConfig[selectedAlert.level].label}</Tag>
              <span style={{ color: '#999' }}>来源: {selectedAlert.source}</span>
              <span style={{ color: '#999' }}>{dayjs(selectedAlert.createdAt).format('YYYY-MM-DD HH:mm:ss')}</span>
            </Space>
            <Typography.Paragraph style={{ fontSize: 15, lineHeight: 1.8 }}>{selectedAlert.summary}</Typography.Paragraph>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default AlertCenter;
