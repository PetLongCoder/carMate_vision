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
import {
  CameraOutlined,
  HighlightOutlined,
  AimOutlined,
  ReloadOutlined,
  SearchOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { PageHeader } from '../components/common';
import { getHistoryTypes, getUserHistory } from '../api/history';
import type { HistoryRecord, HistoryTypeOption } from '../types';

const { RangePicker } = DatePicker;
const { Text } = Typography;

const typeConfig = {
  plate: { color: 'blue' as const, icon: <CameraOutlined />, label: '车牌识别' },
  police_gesture: { color: 'purple' as const, icon: <HighlightOutlined />, label: '交警手势' },
  driver_gesture: { color: 'green' as const, icon: <AimOutlined />, label: '车主手势' },
};

const sourceOptions = [
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'track', label: '视频追踪' },
];

function getResultText(record: HistoryRecord): string {
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

const History: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [types, setTypes] = useState<HistoryTypeOption[]>([]);
  const [recordType, setRecordType] = useState<string | undefined>();
  const [sourceType, setSourceType] = useState<string | undefined>();
  const [success, setSuccess] = useState<boolean | undefined>();
  const [keyword, setKeyword] = useState('');
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [selected, setSelected] = useState<HistoryRecord | null>(null);

  useEffect(() => {
    void getHistoryTypes()
      .then(setTypes)
      .catch(() => message.error('加载识别类型失败'));
  }, []);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getUserHistory({
        page,
        pageSize,
        type: recordType,
        sourceType,
        success,
        keyword: keyword.trim() || undefined,
        startDate: dateRange?.[0]?.startOf('day').toISOString(),
        endDate: dateRange?.[1]?.endOf('day').toISOString(),
      });
      setRecords(data.list);
      setTotal(data.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载历史记录失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, recordType, sourceType, success, keyword, dateRange]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const columns = [
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 130,
      render: (type: keyof typeof typeConfig, record: HistoryRecord) => {
        const cfg = typeConfig[type];
        return (
          <Space direction="vertical" size={0}>
            <Tag color={cfg?.color} icon={cfg?.icon}>
              {record.module_label || cfg?.label || type}
            </Tag>
            {record.source_label && <Tag>{record.source_label}</Tag>}
          </Space>
        );
      },
    },
    {
      title: '结果',
      key: 'result',
      render: (_: unknown, record: HistoryRecord) => (
        <Space direction="vertical" size={0}>
          <Tag style={{ fontSize: 14 }} color={record.success === false ? 'default' : undefined}>
            {getResultText(record)}
          </Tag>
          {record.success === false && <Tag color="error">失败</Tag>}
        </Space>
      ),
    },
    {
      title: '文件名',
      dataIndex: 'file_name',
      key: 'file_name',
      width: 180,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '详情',
      key: 'detail',
      width: 80,
      render: (_: unknown, record: HistoryRecord) => (
        <Button type="link" size="small" onClick={() => setSelected(record)}>
          查看
        </Button>
      ),
    },
  ];

  const resetFilters = () => {
    setRecordType(undefined);
    setSourceType(undefined);
    setSuccess(undefined);
    setKeyword('');
    setDateRange(null);
    setPage(1);
  };

  return (
    <div>
      <PageHeader
        title="历史记录"
        subtitle="查看车牌识别、手势识别的历史操作记录"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void loadHistory()}>
            刷新
          </Button>
        }
      />

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
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
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            style={{ width: 220 }}
            allowClear
          />
          <RangePicker
            value={dateRange}
            onChange={(values) => setDateRange(values as [Dayjs, Dayjs] | null)}
          />
          <Button
            type="primary"
            icon={<HistoryOutlined />}
            onClick={() => {
              setPage(1);
              void loadHistory();
            }}
          >
            查询
          </Button>
          <Button onClick={resetFilters}>重置</Button>
        </Space>
      </Card>

      <Card>
        <Table
          columns={columns}
          dataSource={records}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (count) => `共 ${count} 条`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            },
          }}
        />
      </Card>

      <Drawer title="识别详情" open={!!selected} onClose={() => setSelected(null)} width={520}>
        {selected && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Text type="secondary">类型</Text>
              <div>{selected.module_label || selected.type}</div>
            </div>
            <div>
              <Text type="secondary">来源</Text>
              <div>{selected.source_label || selected.source_type || '-'}</div>
            </div>
            <div>
              <Text type="secondary">结果</Text>
              <div>{getResultText(selected)}</div>
            </div>
            <div>
              <Text type="secondary">文件名</Text>
              <div>{selected.file_name || '-'}</div>
            </div>
            <div>
              <Text type="secondary">时间</Text>
              <div>{dayjs(selected.createdAt).format('YYYY-MM-DD HH:mm:ss')}</div>
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

export default History;
