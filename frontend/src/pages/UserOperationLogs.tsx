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
import { ReloadOutlined, SearchOutlined, AuditOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { PageHeader } from '../components/common';
import { getOperationLogActions, getOperationLogs } from '../api/adminLogs';
import type { OperationLogActionOption, UserOperationLog } from '../types';

const { RangePicker } = DatePicker;
const { Text, Paragraph } = Typography;

const UserOperationLogs: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<UserOperationLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [username, setUsername] = useState('');
  const [action, setAction] = useState<string | undefined>();
  const [success, setSuccess] = useState<boolean | undefined>();
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [actions, setActions] = useState<OperationLogActionOption[]>([]);
  const [selected, setSelected] = useState<UserOperationLog | null>(null);

  useEffect(() => {
    void getOperationLogActions()
      .then(setActions)
      .catch(() => message.error('加载操作类型失败'));
  }, []);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getOperationLogs({
        page,
        pageSize,
        username: username.trim() || undefined,
        action,
        success,
        startDate: dateRange?.[0]?.startOf('day').toISOString(),
        endDate: dateRange?.[1]?.endOf('day').toISOString(),
      });
      setLogs(data.list);
      setTotal(data.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载操作日志失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, username, action, success, dateRange]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '用户',
      dataIndex: 'username',
      key: 'username',
      width: 120,
      render: (value: string | null, record: UserOperationLog) => value || `ID:${record.user_id ?? '-'}`,
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 90,
      render: (role: string | null) =>
        role === 'admin' ? <Tag color="gold">管理员</Tag> : <Tag color="blue">用户</Tag>,
    },
    {
      title: '操作',
      dataIndex: 'action_label',
      key: 'action_label',
      width: 150,
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
      title: 'IP',
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 130,
      render: (value: string | null) => value || '-',
    },
    {
      title: '说明',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '详情',
      key: 'detail',
      width: 80,
      render: (_: unknown, record: UserOperationLog) => (
        <Button type="link" size="small" onClick={() => setSelected(record)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="用户操作日志"
        subtitle="查看各用户的登录、注册、资料修改、绑定解绑等操作记录"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void loadLogs()}>
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
            style={{ width: 180 }}
            allowClear
          />
          <Select
            placeholder="操作类型"
            value={action}
            onChange={setAction}
            allowClear
            style={{ width: 180 }}
            options={actions.map((item) => ({ value: item.value, label: item.label }))}
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
          <RangePicker
            value={dateRange}
            onChange={(values) => setDateRange(values as [Dayjs, Dayjs] | null)}
          />
          <Button
            type="primary"
            icon={<AuditOutlined />}
            onClick={() => {
              setPage(1);
              void loadLogs();
            }}
          >
            查询
          </Button>
          <Button
            onClick={() => {
              setUsername('');
              setAction(undefined);
              setSuccess(undefined);
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
          dataSource={logs}
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

      <Drawer
        title="操作详情"
        open={selected !== null}
        onClose={() => setSelected(null)}
        width={520}
      >
        {selected && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Text type="secondary">用户</Text>
              <div>{selected.username || '-'} ({selected.role || '-'})</div>
            </div>
            <div>
              <Text type="secondary">操作</Text>
              <div>{selected.action_label}</div>
            </div>
            <div>
              <Text type="secondary">时间</Text>
              <div>{dayjs(selected.created_at).format('YYYY-MM-DD HH:mm:ss')}</div>
            </div>
            <div>
              <Text type="secondary">IP / 设备</Text>
              <div>{selected.ip_address || '-'}</div>
              <Paragraph type="secondary" style={{ marginBottom: 0, wordBreak: 'break-all' }}>
                {selected.user_agent || '-'}
              </Paragraph>
            </div>
            {selected.message && (
              <div>
                <Text type="secondary">说明</Text>
                <div>{selected.message}</div>
              </div>
            )}
            {selected.detail && (
              <div>
                <Text type="secondary">附加信息</Text>
                <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 8, overflow: 'auto' }}>
                  {JSON.stringify(selected.detail, null, 2)}
                </pre>
              </div>
            )}
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default UserOperationLogs;
