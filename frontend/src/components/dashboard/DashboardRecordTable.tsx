import React, { useCallback, useEffect, useState } from 'react';
import { Table, Tag, Button, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { useNavigate } from 'react-router-dom';
import { getAdminRecognitionRecords } from '../../api/adminRecognitionRecords';
import type { AdminRecognitionRecord } from '../../types';
import { buildRecognitionRecordsPath } from '../../utils/dashboardNav';

const { Text } = Typography;

interface DashboardRecordTableProps {
  type: string;
  success?: boolean;
  startDate?: string;
  endDate?: string;
}

function getResultText(record: AdminRecognitionRecord): string {
  if (record.summary) return record.summary;
  const result = record.result;
  if (result.plateNo) return String(result.plateNo);
  if (result.gesture) return String(result.gesture);
  return '-';
}

const moduleColors: Record<string, string> = {
  plate: 'blue',
  police_gesture: 'purple',
  driver_gesture: 'green',
};

const DashboardRecordTable: React.FC<DashboardRecordTableProps> = ({
  type,
  success,
  startDate,
  endDate,
}) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<AdminRecognitionRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAdminRecognitionRecords({
        page,
        pageSize: 10,
        type,
        success,
        startDate,
        endDate,
      });
      setRecords(data.list);
      setTotal(data.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载记录失败');
    } finally {
      setLoading(false);
    }
  }, [page, type, success, startDate, endDate]);

  useEffect(() => {
    setPage(1);
  }, [type, success, startDate, endDate]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <Text type="secondary">共 {total} 条记录</Text>
        <Button
          type="link"
          onClick={() =>
            navigate(buildRecognitionRecordsPath({ type, success, startDate, endDate }))
          }
        >
          在识别记录管理中查看全部
        </Button>
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
            render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
          },
          {
            title: '用户',
            dataIndex: 'username',
            width: 100,
            render: (value: string | null, record: AdminRecognitionRecord) =>
              value || (record.user_id ? `ID:${record.user_id}` : '未登录'),
          },
          {
            title: '类型',
            dataIndex: 'module_label',
            width: 110,
            render: (value: string, record: AdminRecognitionRecord) => (
              <Tag color={moduleColors[record.type] || 'default'}>{value || record.type}</Tag>
            ),
          },
          {
            title: '结果',
            dataIndex: 'success',
            width: 80,
            render: (value: boolean) =>
              value ? <Tag color="success">成功</Tag> : <Tag color="error">失败</Tag>,
          },
          {
            title: '摘要',
            key: 'summary',
            ellipsis: true,
            render: (_: unknown, record: AdminRecognitionRecord) => getResultText(record),
          },
        ]}
      />
    </>
  );
};

export default DashboardRecordTable;
