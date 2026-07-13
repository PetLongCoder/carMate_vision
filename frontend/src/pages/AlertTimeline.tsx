import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Timeline, Tag, Space, Button, Segmented, DatePicker, Select, Typography, Spin, Empty,
} from 'antd';
import { ReloadOutlined, EyeOutlined, BellOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../components/common';
import { getAlertTimeline, getAnomalyTypes } from '../api';
import type { Alert, AlertLevel, AnomalyTypeOption } from '../types';
import dayjs from 'dayjs';

const levelConfig: Record<AlertLevel, { color: string; icon: React.ReactNode; label: string }> = {
  info: { color: 'blue', icon: <BellOutlined />, label: '提示' },
  warning: { color: 'orange', icon: <ExclamationCircleOutlined />, label: '警告' },
  critical: { color: 'red', icon: <ExclamationCircleOutlined />, label: '严重' },
};

const AlertTimelinePage: React.FC = () => {
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [typeOptions, setTypeOptions] = useState<AnomalyTypeOption[]>([]);
  const pageSize = 20;

  const loadTimeline = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAlertTimeline({
        page, pageSize,
        level: levelFilter === 'all' ? undefined : levelFilter,
        anomalyType: typeFilter,
      });
      setAlerts(res.data.data.list);
      setTotal(res.data.data.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [page, levelFilter, typeFilter]);

  useEffect(() => {
    void loadTimeline();
  }, [loadTimeline]);

  useEffect(() => {
    getAnomalyTypes()
      .then((res) => setTypeOptions(res.data.data))
      .catch(() => {});
  }, []);

  // Group by date
  const groupedByDate: Record<string, Alert[]> = {};
  alerts.forEach((a) => {
    const dateKey = dayjs(a.createdAt).format('YYYY-MM-DD');
    if (!groupedByDate[dateKey]) groupedByDate[dateKey] = [];
    groupedByDate[dateKey].push(a);
  });

  return (
    <div>
      <PageHeader
        title="告警时间线"
        subtitle="按时间顺序查看系统告警事件"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadTimeline()}>
            刷新
          </Button>
        }
      />

      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
          <Segmented
            options={[
              { label: '全部级别', value: 'all' },
              { label: '提示', value: 'info' },
              { label: '警告', value: 'warning' },
              { label: '严重', value: 'critical' },
            ]}
            value={levelFilter}
            onChange={(v) => { setLevelFilter(v as string); setPage(1); }}
          />
          <Select
            placeholder="异常类型"
            allowClear
            style={{ width: 200 }}
            value={typeFilter}
            onChange={(v) => { setTypeFilter(v); setPage(1); }}
            options={typeOptions.map((t) => ({ value: t.value, label: t.label }))}
          />
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => navigate('/alerts/dashboard')}
          >
            查看仪表盘
          </Button>
        </Space>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin tip="加载中..." /></div>
        ) : alerts.length === 0 ? (
          <Empty description="暂无告警记录" />
        ) : (
          <Timeline
            items={Object.entries(groupedByDate).map(([date, items]) => ({
              children: (
                <div>
                  <Typography.Title level={5} style={{ marginBottom: 12 }}>
                    {date === dayjs().format('YYYY-MM-DD') ? '今天' : date}
                    <Tag style={{ marginLeft: 8 }}>{items.length} 条</Tag>
                  </Typography.Title>
                  {items.map((alert) => {
                    const cfg = levelConfig[alert.level as AlertLevel] || levelConfig.info;
                    return (
                      <Card
                        key={alert.id}
                        size="small"
                        style={{ marginBottom: 8, cursor: 'pointer' }}
                        onClick={() => navigate(`/alerts/detail/${alert.id}`)}
                        hoverable
                      >
                        <Space wrap>
                          <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>
                          <span style={{ fontWeight: 500 }}>{alert.title}</span>
                          {alert.anomalyTypeLabel && (
                            <Tag>{alert.anomalyTypeLabel}</Tag>
                          )}
                          <Typography.Text type="secondary">
                            {dayjs(alert.createdAt).format('HH:mm:ss')}
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            {alert.sourceLabel || alert.source}
                          </Typography.Text>
                          {alert.acknowledged ? (
                            <Tag color="default">已确认</Tag>
                          ) : (
                            <Tag color="processing">未确认</Tag>
                          )}
                        </Space>
                      </Card>
                    );
                  })}
                </div>
              ),
            }))}
          />
        )}

        {total > pageSize && (
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <Space>
              <Button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</Button>
              <span>第 {page} 页 / 共 {Math.ceil(total / pageSize)} 页</span>
              <Button disabled={page * pageSize >= total} onClick={() => setPage((p) => p + 1)}>下一页</Button>
            </Space>
          </div>
        )}
      </Card>
    </div>
  );
};

export default AlertTimelinePage;
