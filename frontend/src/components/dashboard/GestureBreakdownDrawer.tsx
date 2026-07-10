import React, { useCallback, useEffect, useState } from 'react';
import { Drawer, List, Button, Tag, Table, Typography, Space, message } from 'antd';
import { RightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { getPoliceGestureLogs } from '../../api/policeGestureLogs';
import type { GestureBreakdown, TodayGestureBreakdown } from '../../types';
import { buildRecognitionRecordsPath, todayRange } from '../../utils/dashboardNav';

const { Text } = Typography;

export type GestureDrawerMode = 'total' | 'today' | 'success';

interface GestureBreakdownDrawerProps {
  open: boolean;
  mode: GestureDrawerMode;
  breakdown: GestureBreakdown;
  todayBreakdown: TodayGestureBreakdown;
  onClose: () => void;
}

interface CategoryItem {
  key: string;
  label: string;
  description: string;
  count: number;
  color: string;
  action: 'navigate' | 'logs';
  path?: string;
}

const modeTitles: Record<GestureDrawerMode, string> = {
  total: '手势识别分类',
  today: '今日手势识别分类',
  success: '手势识别成功分类',
};

const GestureBreakdownDrawer: React.FC<GestureBreakdownDrawerProps> = ({
  open,
  mode,
  breakdown,
  todayBreakdown,
  onClose,
}) => {
  const navigate = useNavigate();
  const [logsOpen, setLogsOpen] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logs, setLogs] = useState<Awaited<ReturnType<typeof getPoliceGestureLogs>> | null>(null);

  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    try {
      const data = await getPoliceGestureLogs({ page: 1, pageSize: 10 });
      setLogs(data);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载推理日志失败');
    } finally {
      setLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      setLogsOpen(false);
      setLogs(null);
    }
  }, [open]);

  const today = todayRange();

  const categories: CategoryItem[] = (() => {
    if (mode === 'today') {
      return [
        {
          key: 'today-police-history',
          label: '交警手势（识别历史）',
          description: '今日 history_records 中的交警手势记录',
          count: todayBreakdown.policeGestureRecords,
          color: 'purple',
          action: 'navigate',
          path: buildRecognitionRecordsPath({
            type: 'police_gesture',
            ...today,
          }),
        },
        {
          key: 'today-driver-history',
          label: '车主手势（识别历史）',
          description: '今日 history_records 中的车主手势记录',
          count: todayBreakdown.driverGestureRecords,
          color: 'green',
          action: 'navigate',
          path: buildRecognitionRecordsPath({
            type: 'driver_gesture',
            ...today,
          }),
        },
        {
          key: 'today-police-logs',
          label: '交警手势（推理日志）',
          description: '今日 police_gesture_logs 推理明细',
          count: todayBreakdown.policeGestureLogs,
          color: 'geekblue',
          action: 'logs',
        },
      ];
    }

    if (mode === 'success') {
      return [
        {
          key: 'success-police-history',
          label: '交警手势（识别成功）',
          description: '识别历史中的成功交警手势记录',
          count: breakdown.policeGestureRecords,
          color: 'purple',
          action: 'navigate',
          path: buildRecognitionRecordsPath({ type: 'police_gesture', success: true }),
        },
        {
          key: 'success-driver-history',
          label: '车主手势（识别成功）',
          description: '识别历史中的成功车主手势记录',
          count: breakdown.driverGestureRecords,
          color: 'green',
          action: 'navigate',
          path: buildRecognitionRecordsPath({ type: 'driver_gesture', success: true }),
        },
        {
          key: 'success-police-logs',
          label: '交警手势（推理成功）',
          description: 'police_gesture_logs 中 success=true 的记录',
          count: breakdown.policeGestureLogsSuccess,
          color: 'cyan',
          action: 'logs',
        },
      ];
    }

    return [
      {
        key: 'police-history',
        label: '交警手势（识别历史）',
        description: '用户识别历史中的交警手势记录',
        count: breakdown.policeGestureRecords,
        color: 'purple',
        action: 'navigate',
        path: buildRecognitionRecordsPath({ type: 'police_gesture' }),
      },
      {
        key: 'driver-history',
        label: '车主手势（识别历史）',
        description: '用户识别历史中的车主手势记录',
        count: breakdown.driverGestureRecords,
        color: 'green',
        action: 'navigate',
        path: buildRecognitionRecordsPath({ type: 'driver_gesture' }),
      },
      {
        key: 'police-logs',
        label: '交警手势（推理日志）',
        description: '模型推理产生的交警手势明细日志',
        count: breakdown.policeGestureLogs,
        color: 'geekblue',
        action: 'logs',
      },
    ];
  })();

  const handleCategoryClick = (item: CategoryItem) => {
    if (item.action === 'navigate' && item.path) {
      onClose();
      navigate(item.path);
      return;
    }
    setLogsOpen(true);
    void loadLogs();
  };

  return (
    <>
      <Drawer
        title={modeTitles[mode]}
        open={open}
        onClose={onClose}
        width={480}
        extra={<Text type="secondary">点击分类查看明细</Text>}
      >
        <List
          dataSource={categories}
          renderItem={(item) => (
            <List.Item
              style={{ cursor: 'pointer', padding: '12px 0' }}
              onClick={() => handleCategoryClick(item)}
              actions={[
                <Button type="link" icon={<RightOutlined />} key="view">
                  查看
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Tag color={item.color}>{item.label}</Tag>
                    <Text strong style={{ fontSize: 18 }}>
                      {item.count}
                    </Text>
                  </Space>
                }
                description={item.description}
              />
            </List.Item>
          )}
        />
      </Drawer>

      <Drawer
        title="交警手势推理日志"
        open={logsOpen}
        onClose={() => setLogsOpen(false)}
        width={720}
      >
        <Table
          rowKey="id"
          loading={logsLoading}
          dataSource={logs?.list ?? []}
          pagination={{ pageSize: 10, total: logs?.total }}
          columns={[
            {
              title: '时间',
              dataIndex: 'createdAt',
              width: 170,
              render: (value: string | null) =>
                value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-',
            },
            { title: '手势', dataIndex: 'gesture', width: 100 },
            {
              title: '类型',
              dataIndex: 'recognitionType',
              width: 110,
              render: (value: string) => <Tag>{value}</Tag>,
            },
            {
              title: '结果',
              dataIndex: 'success',
              width: 80,
              render: (value: boolean) =>
                value ? <Tag color="success">成功</Tag> : <Tag color="error">失败</Tag>,
            },
            {
              title: '置信度',
              dataIndex: 'confidence',
              width: 90,
              render: (value?: number) => (value != null ? `${(value * 100).toFixed(1)}%` : '-'),
            },
          ]}
        />
      </Drawer>
    </>
  );
};

export default GestureBreakdownDrawer;
