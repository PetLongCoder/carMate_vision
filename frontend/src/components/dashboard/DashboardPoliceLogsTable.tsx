import React, { useCallback, useEffect, useState } from 'react';
import { Table, Tag, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { getPoliceGestureLogs } from '../../api/policeGestureLogs';

const { Text } = Typography;

const DashboardPoliceLogsTable: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<Awaited<ReturnType<typeof getPoliceGestureLogs>>['list']>(
    [],
  );
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getPoliceGestureLogs({ page, pageSize: 10 });
      setRecords(data.list);
      setTotal(data.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载推理日志失败');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <Text type="secondary">共 {total} 条推理日志</Text>
      </div>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={records}
        pagination={{
          current: page,
          pageSize: 10,
          total,
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
