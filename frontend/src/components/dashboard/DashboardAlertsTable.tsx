import React, { useCallback, useEffect, useState } from 'react';
import { Table, Tag, Button, Typography, message } from 'antd';
import { BellOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useNavigate } from 'react-router-dom';
import { getAlerts } from '../../api';
import type { Alert, AlertLevel } from '../../types';
import { buildAlertsPath } from '../../utils/dashboardNav';

const { Text } = Typography;

const levelConfig: Record<AlertLevel, { color: string; icon: React.ReactNode; label: string }> = {
  info: { color: 'blue', icon: <BellOutlined />, label: '提示' },
  warning: { color: 'orange', icon: <ExclamationCircleOutlined />, label: '警告' },
  critical: { color: 'red', icon: <ExclamationCircleOutlined />, label: '严重' },
};

interface DashboardAlertsTableProps {
  acknowledged?: boolean;
}

const DashboardAlertsTable: React.FC<DashboardAlertsTableProps> = ({ acknowledged }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAlerts({ page: 1, pageSize: 10, acknowledged });
      setAlerts(res.data.data.list);
      setTotal(res.data.data.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载告警失败');
    } finally {
      setLoading(false);
    }
  }, [acknowledged]);

  useEffect(() => {
    void loadAlerts();
  }, [loadAlerts]);

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <Text type="secondary">共 {total} 条告警</Text>
        <Button type="link" onClick={() => navigate(buildAlertsPath({ acknowledged }))}>
          在告警中心查看全部
        </Button>
      </div>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={alerts}
        pagination={false}
        columns={[
          {
            title: '级别',
            dataIndex: 'level',
            width: 80,
            render: (level: AlertLevel) => {
              const cfg = levelConfig[level];
              return (
                <Tag color={cfg.color} icon={cfg.icon}>
                  {cfg.label}
                </Tag>
              );
            },
          },
          { title: '标题', dataIndex: 'title', ellipsis: true },
          { title: '来源', dataIndex: 'source', width: 120 },
          {
            title: '时间',
            dataIndex: 'createdAt',
            width: 170,
            render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
          },
          {
            title: '状态',
            dataIndex: 'acknowledged',
            width: 90,
            render: (value: boolean) =>
              value ? <Tag color="default">已确认</Tag> : <Tag color="processing">未读</Tag>,
          },
        ]}
      />
    </>
  );
};

export default DashboardAlertsTable;
