import React, { useCallback, useEffect, useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Space,
  Input,
  Select,
  Button,
  Drawer,
  Typography,
  DatePicker,
  message,
} from 'antd';
import { ReloadOutlined, SearchOutlined, FileSearchOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { PageHeader } from '../components/common';
import {
  getAdminRecognitionRecords,
  getAdminRecognitionTypes,
} from '../api/adminRecognitionRecords';
import type { AdminRecognitionRecord, HistoryTypeOption } from '../types';

const { RangePicker } = DatePicker;
const { Text } = Typography;

const moduleColors: Record<string, string> = {
  plate: 'blue',
  police_gesture: 'purple',
  driver_gesture: 'green',
};

const sourceOptions = [
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'track', label: '视频追踪' },
];

function getResultText(record: AdminRecognitionRecord): string {
  if (record.summary) {
    return record.summary;
  }
  const result = record.result;
  if (result.plateNo) {
    return String(result.plateNo);
  }
  const plates = result.plates as Array<{ plateNo?: string }> | undefined;
  if (plates?.length) {
    return plates.map((p) => p.plateNo || '未知').join('、');
  }
  if (result.gesture) {
    return String(result.gesture);
  }
  return '-';
}

const AdminRecognitionRecords: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<AdminRecognitionRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [types, setTypes] = useState<HistoryTypeOption[]>([]);
  const [username, setUsername] = useState('');
  const [recordType, setRecordType] = useState<string | undefined>();
  const [sourceType, setSourceType] = useState<string | undefined>();
  const [success, setSuccess] = useState<boolean | undefined>();
  const [keyword, setKeyword] = useState('');
  const [plateNo, setPlateNo] = useState('');
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [selected, setSelected] = useState<AdminRecognitionRecord | null>(null);

  useEffect(() => {
    void getAdminRecognitionTypes()
      .then(setTypes)
      .catch(() => message.error('加载识别类型失败'));
  }, []);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAdminRecognitionRecords({
        page,
        pageSize,
        type: recordType,
        sourceType,
        success,
        keyword: keyword.trim() || undefined,
        username: username.trim() || undefined,
        plateNo: plateNo.trim() || undefined,
        startDate: dateRange?.[0]?.startOf('day').toISOString(),
        endDate: dateRange?.[1]?.endOf('day').toISOString(),
      });
      setRecords(data.list);
      setTotal(data.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载识别记录失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, recordType, sourceType, success, keyword, plateNo, username, dateRange]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  const columns = [
    {
      title: '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 170,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '用户',
      dataIndex: 'username',
      key: 'username',
      width: 120,
      render: (value: string | null, record: AdminRecognitionRecord) =>
        value || (record.user_id ? `ID:${record.user_id}` : '未登录'),
    },
    {
      title: '类型',
      dataIndex: 'module_label',
      key: 'module_label',
      width: 120,
      render: (value: string, record: AdminRecognitionRecord) => (
        <Tag color={moduleColors[record.type] || 'default'}>{value || record.type}</Tag>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source_label',
      key: 'source_label',
      width: 90,
      render: (value: string | null) => value || '-',
    },
    {
      title: '结果',
      dataIndex: 'success',
      key: 'success',
      width: 80,
      render: (value: boolean) =>
        value ? <Tag color="success">成功</Tag> : <Tag color="error">失败</Tag>,
    },
    {
      title: '摘要',
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: true,
      render: (_: string | null, record: AdminRecognitionRecord) => getResultText(record),
    },
    {
      title: '文件名',
      dataIndex: 'file_name',
      key: 'file_name',
      width: 160,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '详情',
      key: 'detail',
      width: 80,
      render: (_: unknown, record: AdminRecognitionRecord) => (
        <Button type="link" size="small" onClick={() => setSelected(record)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="识别记录管理"
        subtitle="查看全部用户的车牌识别、手势识别记录"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void loadRecords()}>
            刷新
          </Button>
        }
      />

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="用户名"
            prefix={<SearchOutlined />}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ width: 160 }}
            allowClear
          />
          <Select
            placeholder="识别类型"
            value={recordType}
            onChange={setRecordType}
            allowClear
            style={{ width: 160 }}
            options={types.map((item) => ({ value: item.value, label: item.label }))}
          />
          <Select
            placeholder="来源"
            value={sourceType}
            onChange={setSourceType}
            allowClear
            style={{ width: 140 }}
            options={sourceOptions}
          />
          <Select
            placeholder="结果"
            value={success}
            onChange={setSuccess}
            allowClear
            style={{ width: 120 }}
            options={[
              { value: true, label: '成功' },
              { value: false, label: '失败' },
            ]}
          />
          <Input
            placeholder="关键词（文件名/结果）"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Input
            placeholder="车牌号"
            prefix={<SearchOutlined />}
            value={plateNo}
            onChange={(e) => setPlateNo(e.target.value)}
            style={{ width: 180 }}
            allowClear
          />
          <RangePicker
            value={dateRange}
            onChange={(values) => setDateRange(values as [Dayjs, Dayjs] | null)}
          />
          <Button
            type="primary"
            icon={<FileSearchOutlined />}
            onClick={() => {
              setPage(1);
              void loadRecords();
            }}
          >
            查询
          </Button>
          <Button
            onClick={() => {
              setUsername('');
              setRecordType(undefined);
              setSourceType(undefined);
              setSuccess(undefined);
              setKeyword('');
              setPlateNo('');
              setDateRange(null);
              setPage(1);
            }}
          >
            重置
          </Button>
        </Space>
      </Card>

      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={records}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (count) => `共 ${count} 条`,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </Card>

      <Drawer title="识别详情" open={!!selected} onClose={() => setSelected(null)} width={520}>
        {selected && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Text type="secondary">用户</Text>
              <div>{selected.username || (selected.user_id ? `ID:${selected.user_id}` : '未登录')}</div>
            </div>
            <div>
              <Text type="secondary">类型</Text>
              <div>{selected.module_label || selected.type}</div>
            </div>
            <div>
              <Text type="secondary">摘要</Text>
              <div>{getResultText(selected)}</div>
            </div>
            <div>
              <Text type="secondary">完整数据</Text>
              <pre
                style={{
                  background: '#f5f5f5',
                  padding: 12,
                  borderRadius: 8,
                  overflow: 'auto',
                  maxHeight: 360,
                }}
              >
                {JSON.stringify(selected.result, null, 2)}
              </pre>
            </div>
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default AdminRecognitionRecords;
