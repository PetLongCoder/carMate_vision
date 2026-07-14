import React, { useCallback, useEffect, useState } from 'react';
import { Row, Col, Card, Spin, Button, Typography } from 'antd';
import {
  AlertOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { PageHeader } from '../components/common';
import { getAlertStats } from '../api';
import type { AlertStats, AlertLevel } from '../types';

const levelColors: Record<AlertLevel, string> = {
  info: '#1677ff',
  warning: '#faad14',
  critical: '#ff4d4f',
};

const AlertDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadStats = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await getAlertStats({ days: 7 });
      setStats(res.data.data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16, color: '#999' }}>加载告警统计数据...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Typography.Text type="danger">加载告警数据失败，请确认后端服务已启动</Typography.Text>
        <div style={{ marginTop: 16 }}>
          <Button icon={<ReloadOutlined />} onClick={() => void loadStats()}>重试</Button>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16, color: '#999' }}>加载告警统计数据...</div>
      </div>
    );
  }

  // 即使是 0 也要显示空状态
  const hasData = stats.total > 0;

  const levelPieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        name: '告警级别',
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 16, fontWeight: 'bold' } },
        data: [
          { value: stats.totalByLevel.info || 0, name: '提示', itemStyle: { color: levelColors.info } },
          { value: stats.totalByLevel.warning || 0, name: '警告', itemStyle: { color: levelColors.warning } },
          { value: stats.totalByLevel.critical || 0, name: '严重', itemStyle: { color: levelColors.critical } },
        ],
      },
    ],
  };

  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['提示', '警告', '严重'], bottom: 0 },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: stats.dailyTrend.map((d) => d.date.slice(5)),
      axisLabel: { rotate: 30, fontSize: 10 },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        name: '提示', type: 'line', data: stats.dailyTrend.map((d) => d.info),
        smooth: true, symbol: 'circle', symbolSize: 6,
        itemStyle: { color: levelColors.info },
      },
      {
        name: '警告', type: 'line', data: stats.dailyTrend.map((d) => d.warning),
        smooth: true, symbol: 'circle', symbolSize: 6,
        itemStyle: { color: levelColors.warning },
      },
      {
        name: '严重', type: 'line', data: stats.dailyTrend.map((d) => d.critical),
        smooth: true, symbol: 'circle', symbolSize: 6,
        itemStyle: { color: levelColors.critical },
      },
    ],
  };

  const typeEntries = Object.entries(stats.byAnomalyType || {}).sort((a, b) => b[1] - a[1]);
  const typeBarOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 120, right: 30, top: 10, bottom: 20 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: {
      type: 'category',
      data: typeEntries.map(([k]) => {
        const short = k.replace('plate_', '').replace('gesture_', '').replace('police_', '').replace('driver_', '');
        return short.length > 15 ? short.slice(0, 15) + '...' : short;
      }).reverse(),
      axisLabel: { fontSize: 10 },
    },
    series: [
      {
        type: 'bar',
        data: typeEntries.map(([, v]) => v).reverse(),
        itemStyle: { color: '#1677ff', borderRadius: [0, 4, 4, 0] },
      },
    ],
  };

  return (
    <div>
      <PageHeader
        title="告警仪表盘"
        subtitle="系统告警统计与趋势分析"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadStats()}>
            刷新
          </Button>
        }
      />

      {!hasData && (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <AlertOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
          <Typography.Paragraph type="secondary" style={{ marginTop: 16, fontSize: 16 }}>
            暂无告警记录
          </Typography.Paragraph>
          <Typography.Text type="secondary">当前用户尚未触发任何告警事件</Typography.Text>
        </div>
      )}

      {hasData && (
        <>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card hoverable onClick={() => navigate('/alerts')}>
            <div style={{ textAlign: 'center' }}>
              <AlertOutlined style={{ fontSize: 32, color: '#1677ff' }} />
              <div style={{ fontSize: 28, fontWeight: 700, margin: '8px 0' }}>{stats.total}</div>
              <Typography.Text type="secondary">告警总数</Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable onClick={() => navigate('/alerts?acknowledged=false')}>
            <div style={{ textAlign: 'center' }}>
              <WarningOutlined style={{ fontSize: 32, color: '#faad14' }} />
              <div style={{ fontSize: 28, fontWeight: 700, margin: '8px 0' }}>{stats.unacknowledged}</div>
              <Typography.Text type="secondary">未确认告警</Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <ClockCircleOutlined style={{ fontSize: 32, color: '#52c41a' }} />
              <div style={{ fontSize: 28, fontWeight: 700, margin: '8px 0' }}>{stats.todayCount}</div>
              <Typography.Text type="secondary">今日新增</Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <CheckCircleOutlined style={{ fontSize: 32, color: '#13c2c2' }} />
              <div style={{ fontSize: 28, fontWeight: 700, margin: '8px 0' }}>
                {stats.avgResponseMinutes > 0 ? `${stats.avgResponseMinutes}m` : '-'}
              </div>
              <Typography.Text type="secondary">平均响应时间</Typography.Text>
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="告警级别分布" size="small">
            <ReactECharts option={levelPieOption} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="7日告警趋势" size="small">
            <ReactECharts option={trendOption} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="异常类型分布" size="small">
            <ReactECharts option={typeBarOption} style={{ height: 280 }} />
          </Card>
        </Col>
      </Row>
        </>
      )}
    </div>
  );
};

export default AlertDashboard;
