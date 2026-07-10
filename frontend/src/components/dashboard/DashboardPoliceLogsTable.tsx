import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Table, Tag, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { getPoliceGestureLogs } from '../../api/policeGestureLogs';
import type { PoliceGestureLogItem } from '../../api/policeGestureLogs';

const { Text } = Typography;

interface DashboardPoliceLogsTableProps {
  todayOnly?: boolean;
  successOnly?: boolean;
}

const DashboardPoliceLogsTable: React.FC<DashboardPoliceLogsTableProps> = ({
  todayOnly = false,
  successOnly = false,
}) => {
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<PoliceGestureLogItem[]>([]);
  const [page, setPage] = useState(1);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getPoliceGestureLogs({ page: 1, pageSize: 100 });
      setRecords(data.list);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载推理日志失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  useEffect(() => {
    setPage(1);
  }, [todayOnly, successOnly]);

  const filtered = useMemo(() => {
    let list = records;
    if (todayOnly) {
      list = list.filter((item) => item.createdAt && dayjs(item.createdAt).isSame(dayjs(), 'day'));
    }
    if (successOnly) {
      list = list.filter((item) => item.success);
    }
    return list;
  }, [records, todayOnly, successOnly]);

  const pageData = filtered.slice((page - 1) * 10, page * 10);

  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <Text type="secondary">共 {filtered.length} 条推理日志</Text>
      </div>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={pageData}
        pagination={{
          current: page,
          pageSize: 10,
          total: filtered.length,
          onChange: setPage,
          showSizeChanger: false,
        }}
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
          {
            title: '文件',
            dataIndex: 'filename',
            ellipsis: true,
            render: (value: string | null) => value || '-',
          },
        ]}
      />
    </>
  );
};

export default DashboardPoliceLogsTable;
