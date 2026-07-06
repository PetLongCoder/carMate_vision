import React, { useState } from 'react';
import { Card, Table, Tag, Space, Segmented } from 'antd';
import { CameraOutlined, HighlightOutlined, AimOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/common';
import type { HistoryRecord } from '../types';
import dayjs from 'dayjs';

const mockHistory: HistoryRecord[] = [
  { id: 1, type: 'plate', image: '', result: { plateNo: '沪A12345', color: 'blue' }, createdAt: dayjs().subtract(10, 'minute').toISOString() },
  { id: 2, type: 'police_gesture', image: '', result: { gesture: '左转', confidence: 0.95 }, createdAt: dayjs().subtract(25, 'minute').toISOString() },
  { id: 3, type: 'driver_gesture', image: '', result: { gesture: '音量调高', controlType: 'volume_up' }, createdAt: dayjs().subtract(1, 'hour').toISOString() },
  { id: 4, type: 'plate', image: '', result: { plateNo: '京B67890', color: 'green' }, createdAt: dayjs().subtract(2, 'hour').toISOString() },
  { id: 5, type: 'driver_gesture', image: '', result: { gesture: '下一首', controlType: 'next_track' }, createdAt: dayjs().subtract(3, 'hour').toISOString() },
];

const typeConfig = {
  plate: { color: 'blue' as const, icon: <CameraOutlined />, label: '车牌识别' },
  police_gesture: { color: 'purple' as const, icon: <HighlightOutlined />, label: '交警手势' },
  driver_gesture: { color: 'green' as const, icon: <AimOutlined />, label: '车主手势' },
};

const History: React.FC = () => {
  const [filter, setFilter] = useState<string>('all');

  const filtered = filter === 'all' ? mockHistory : mockHistory.filter((r) => r.type === filter);

  const columns = [
    { title: '类型', dataIndex: 'type', key: 'type', width: 120,
      render: (type: keyof typeof typeConfig) => {
        const cfg = typeConfig[type];
        return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>;
      } },
    { title: '结果', dataIndex: 'result', key: 'result',
      render: (result: Record<string, unknown>) => {
        const text = (result.plateNo || result.gesture || '-') as string;
        return <Tag style={{ fontSize: 14 }}>{text}</Tag>;
      } },
    { title: '时间', dataIndex: 'createdAt', key: 'createdAt', width: 180,
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss') },
  ];

  return (
    <div>
      <PageHeader title="历史记录" subtitle="查看车牌识别、手势识别的历史操作记录" />
      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Segmented options={[
            { label: '全部', value: 'all' }, { label: '车牌识别', value: 'plate' },
            { label: '交警手势', value: 'police_gesture' }, { label: '车主手势', value: 'driver_gesture' },
          ]} value={filter} onChange={(v) => setFilter(v as string)} />
        </Space>
        <Table columns={columns} dataSource={filtered} rowKey="id" pagination={{ pageSize: 10 }} />
      </Card>
    </div>
  );
};

export default History;
