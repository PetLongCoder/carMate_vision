import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Descriptions, Tag, Space, Button, Typography, Spin, Result, Steps, Collapse, Empty, Alert as AntAlert,
} from 'antd';
import {
  ArrowLeftOutlined, CheckCircleOutlined, ReloadOutlined,
  BellOutlined, ExclamationCircleOutlined, InfoCircleOutlined,
} from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { getAlertDetail, acknowledgeAlert, getAlertTimeline } from '../api';
import type { Alert, AlertLevel } from '../types';
import dayjs from 'dayjs';

const levelConfig: Record<AlertLevel, { color: string; icon: React.ReactNode; label: string }> = {
  info: { color: 'blue', icon: <BellOutlined />, label: '提示' },
  warning: { color: 'orange', icon: <ExclamationCircleOutlined />, label: '警告' },
  critical: { color: 'red', icon: <ExclamationCircleOutlined />, label: '严重' },
};

const AlertDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [alert, setAlert] = useState<(Alert & { rawEvent?: object; relatedAlerts?: Alert[] }) | null>(null);
  const [loading, setLoading] = useState(true);
  const [acking, setAcking] = useState(false);

  const loadDetail = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await getAlertDetail(Number(id));
      setAlert(res.data.data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  const handleAcknowledge = async () => {
    if (!id) return;
    setAcking(true);
    try {
      await acknowledgeAlert(Number(id));
      void loadDetail();
    } catch {
      // ignore
    } finally {
      setAcking(false);
    }
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 100 }}><Spin size="large" /></div>;
  }

  if (!alert) {
    return <Result status="404" title="告警不存在" subTitle="该告警记录未找到" />;
  }

  const cfg = levelConfig[alert.level as AlertLevel] || levelConfig.info;
  const actions = alert.suggestedActions || [];

  // Timeline data
  const timelineSteps = [
    {
      title: '告警发生',
      description: dayjs(alert.createdAt).format('YYYY-MM-DD HH:mm:ss'),
      status: 'finish' as const,
    },
    {
      title: alert.acknowledged ? '已确认' : '待确认',
      description: alert.acknowledged
        ? `${alert.acknowledgedBy || ''} 于 ${alert.acknowledgedAt ? dayjs(alert.acknowledgedAt).format('YYYY-MM-DD HH:mm:ss') : ''}`
        : '该告警尚未确认',
      status: alert.acknowledged ? 'finish' as const : 'process' as const,
    },
    ...(alert.notifiedChannels?.length
      ? [{
          title: '通知已发送',
          description: `已通过 ${alert.notifiedChannels.join(', ')} 渠道推送告警通知`,
          status: 'finish' as const,
        }]
      : []),
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>返回</Button>
        <Typography.Title level={4} style={{ margin: 0 }}>告警详情</Typography.Title>
      </div>

      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {/* Basic info */}
        <Card title="基本信息">
          <Descriptions column={{ xs: 1, sm: 2 }}>
            <Descriptions.Item label="告警级别">
              <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="标题">{alert.title}</Descriptions.Item>
            <Descriptions.Item label="异常类型">
              {alert.anomalyTypeLabel || alert.anomalyType || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="来源模块">
              {alert.sourceLabel || alert.source || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="影响范围">
              {alert.impactScope || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="发生时间">
              {dayjs(alert.createdAt).format('YYYY-MM-DD HH:mm:ss')}
            </Descriptions.Item>
            <Descriptions.Item label="确认状态">
              {alert.acknowledged ? (
                <Tag color="default" icon={<CheckCircleOutlined />}>已确认</Tag>
              ) : (
                <Tag color="processing">未确认</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="通知渠道">
              {alert.notifiedChannels?.length ? alert.notifiedChannels.join(', ') : '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* Summary */}
        <Card title="告警摘要">
          <Typography.Paragraph style={{ fontSize: 15, lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
            {alert.summary}
          </Typography.Paragraph>
        </Card>

        {/* Suggested actions */}
        {actions.length > 0 && (
          <Card title="建议处置措施">
            <Steps
              direction="vertical"
              current={-1}
              items={actions.map((action: string, i: number) => ({
                title: action,
                status: 'process' as const,
              }))}
            />
          </Card>
        )}

        {/* Event replay - raw event data */}
        {alert.rawEvent && (
          <Card title="事件回放（原始数据）">
            <Collapse
              items={[{
                key: 'raw',
                label: '原始事件数据',
                children: (
                  <pre style={{ maxHeight: 400, overflow: 'auto', background: '#f5f5f5', borderRadius: 8, padding: 12, fontSize: 12 }}>
                    {JSON.stringify(alert.rawEvent, null, 2)}
                  </pre>
                ),
              }]}
            />
          </Card>
        )}

        {/* Timeline */}
        <Card title="事件时间线">
          <Steps
            direction="vertical"
            current={alert.acknowledged ? timelineSteps.length : 1}
            items={timelineSteps}
          />
        </Card>

        {/* Related alerts */}
        {alert.relatedAlerts && alert.relatedAlerts.length > 0 && (
          <Card title="相关告警">
            {alert.relatedAlerts.map((ra) => {
              const rcfg = levelConfig[ra.level as AlertLevel] || levelConfig.info;
              return (
                <Card
                  key={ra.id}
                  size="small"
                  style={{ marginBottom: 8, cursor: 'pointer' }}
                  hoverable
                  onClick={() => navigate(`/alerts/detail/${ra.id}`)}
                >
                  <Space wrap>
                    <Tag color={rcfg.color}>{rcfg.label}</Tag>
                    <span>{ra.title}</span>
                    <Typography.Text type="secondary">
                      {dayjs(ra.createdAt).format('MM-DD HH:mm')}
                    </Typography.Text>
                  </Space>
                </Card>
              );
            })}
          </Card>
        )}

        {/* Acknowledge button */}
        {!alert.acknowledged && (
          <div style={{ textAlign: 'center' }}>
            <Button
              type="primary"
              size="large"
              icon={<CheckCircleOutlined />}
              loading={acking}
              onClick={handleAcknowledge}
            >
              确认告警
            </Button>
          </div>
        )}
      </Space>
    </div>
  );
};

export default AlertDetail;
