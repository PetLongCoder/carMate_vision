import React, { useCallback, useEffect, useState } from 'react';
import { Card, Table, Tag, Space, Button, Modal, Typography, Segmented, message, Steps } from 'antd';
import {
  CheckCircleOutlined, ExclamationCircleOutlined, BellOutlined, ReloadOutlined,
  DashboardOutlined, FieldTimeOutlined, PieChartOutlined, EyeOutlined,
} from '@ant-design/icons';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '../components/common';
import { acknowledgeAlert, getAlerts, batchAcknowledgeAlerts } from '../api';
import type { Alert, AlertLevel } from '../types';
import dayjs from 'dayjs';

const levelConfig: Record<AlertLevel, { color: string; icon: React.ReactNode; label: string }> = {
  info: { color: 'blue', icon: <BellOutlined />, label: '提示' },
  warning: { color: 'orange', icon: <ExclamationCircleOutlined />, label: '警告' },
  critical: { color: 'red', icon: <ExclamationCircleOutlined />, label: '严重' },
};

const AlertCenter: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [ackFilter, setAckFilter] = useState<'all' | 'unread' | 'read'>('all');
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);

  useEffect(() => {
    const acknowledged = searchParams.get('acknowledged');
    if (acknowledged === 'false') {
      setAckFilter('unread');
    } else if (acknowledged === 'true') {
      setAckFilter('read');
    }
  }, [searchParams]);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const acknowledged =
        ackFilter === 'unread' ? false : ackFilter === 'read' ? true : undefined;
      const data = await getAlerts({
        page: 1,
        pageSize: 100,
        level: filter === 'all' ? undefined : filter,
        acknowledged,
      });
      setAlerts(data.data.data.list);
      setTotal(data.data.data.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载告警失败');
    } finally {
      setLoading(false);
    }
  }, [ackFilter, filter]);

  useEffect(() => {
    void loadAlerts();
  }, [loadAlerts]);

  const columns = [
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
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
    { title: '标题', dataIndex: 'title', key: 'title', width: 200 },
    { title: '来源', dataIndex: 'sourceLabel', key: 'source', width: 100 },
    {
      title: '异常类型',
      dataIndex: 'anomalyTypeLabel',
      key: 'anomalyType',
      width: 120,
      render: (v: string) => v ? <Tag>{v}</Tag> : '-',
    },
    {
      title: '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 160,
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '状态',
      dataIndex: 'acknowledged',
      key: 'acknowledged',
      width: 80,
      render: (ack: boolean) =>
        ack ? <Tag color="default">已确认</Tag> : <Tag color="processing">未确认</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: Alert) => (
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/alerts/detail/${record.id}`);
          }}
        >
          详情
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="告警中心"
        subtitle="实时接收系统告警，查看告警摘要和详情"
        extra={
          <Space wrap>
            <Button
              icon={<DashboardOutlined />}
              onClick={() => navigate('/alerts/dashboard')}
            >
              仪表盘
            </Button>
            <Button
              icon={<FieldTimeOutlined />}
              onClick={() => navigate('/alerts/timeline')}
            >
              时间线
            </Button>
            <Button
              icon={<PieChartOutlined />}
              onClick={() => navigate('/alerts/analysis')}
            >
              分析
            </Button>
            {selectedRowKeys.length > 0 && (
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={async () => {
                  try {
                    await batchAcknowledgeAlerts(selectedRowKeys);
                    message.success(`已确认 ${selectedRowKeys.length} 条告警`);
                    setSelectedRowKeys([]);
                    void loadAlerts();
                  } catch {
                    message.error('批量确认失败');
                  }
                }}
              >
                批量确认 ({selectedRowKeys.length})
              </Button>
            )}
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadAlerts()}>
              刷新
            </Button>
          </Space>
        }
      />

      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
          <Segmented
            options={[
              { label: '全部', value: 'all' },
              { label: '提示', value: 'info' },
              { label: '警告', value: 'warning' },
              { label: '严重', value: 'critical' },
            ]}
            value={filter}
            onChange={(v) => setFilter(v as string)}
          />
          <Segmented
            options={[
              { label: '全部状态', value: 'all' },
              { label: '未读', value: 'unread' },
              { label: '已确认', value: 'read' },
            ]}
            value={ackFilter}
            onChange={(v) => setAckFilter(v as 'all' | 'unread' | 'read')}
          />
        </Space>

        <Table
          columns={columns}
          dataSource={alerts}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, total }}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as number[]),
            getCheckboxProps: (record) => ({
              disabled: record.acknowledged,
            }),
          }}
          onRow={(record) => ({
            onClick: () => setSelectedAlert(record),
            style: { cursor: 'pointer', fontWeight: record.acknowledged ? 'normal' : 600 },
          })}
        />
      </Card>

      <Modal
        title={selectedAlert?.title}
        open={!!selectedAlert}
        onCancel={() => setSelectedAlert(null)}
        footer={[
          <Button key="close" onClick={() => setSelectedAlert(null)}>
            关闭
          </Button>,
          selectedAlert && !selectedAlert.acknowledged ? (
            <Button
              key="ack"
              type="primary"
              icon={<CheckCircleOutlined />}
              onClick={async () => {
                if (!selectedAlert) return;
                try {
                  await acknowledgeAlert(selectedAlert.id);
                  message.success('告警已确认');
                  setSelectedAlert(null);
                  void loadAlerts();
                } catch (err) {
                  message.error(err instanceof Error ? err.message : '确认告警失败');
                }
              }}
            >
              确认告警
            </Button>
          ) : null,
        ]}
        width={600}
      >
        {selectedAlert && (
          <div>
            <Space style={{ marginBottom: 16 }}>
              <Tag color={levelConfig[selectedAlert.level].color}>
                {levelConfig[selectedAlert.level].label}
              </Tag>
              <span style={{ color: '#999' }}>来源: {selectedAlert.sourceLabel || selectedAlert.source}</span>
              {selectedAlert.anomalyTypeLabel && (
                <Tag>{selectedAlert.anomalyTypeLabel}</Tag>
              )}
              <span style={{ color: '#999' }}>
                {dayjs(selectedAlert.createdAt).format('YYYY-MM-DD HH:mm:ss')}
              </span>
            </Space>
            <Typography.Paragraph style={{ fontSize: 15, lineHeight: 1.8 }}>
              {selectedAlert.summary}
            </Typography.Paragraph>
            {selectedAlert.impactScope && (
              <div style={{ marginBottom: 12 }}>
                <Typography.Text strong>影响范围：</Typography.Text>
                <Tag color="orange">{selectedAlert.impactScope}</Tag>
              </div>
            )}
            {selectedAlert.suggestedActions && selectedAlert.suggestedActions.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <Typography.Text strong>建议处置措施：</Typography.Text>
                <Steps
                  size="small"
                  direction="vertical"
                  current={-1}
                  style={{ marginTop: 8 }}
                  items={selectedAlert.suggestedActions.map((action: string) => ({
                    title: action,
                    status: 'process' as const,
                  }))}
                />
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default AlertCenter;
