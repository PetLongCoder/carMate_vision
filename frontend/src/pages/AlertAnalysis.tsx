import React, { useCallback, useEffect, useState } from 'react';
import { Row, Col, Card, Typography, Spin, Button, Table, Tag, Progress } from 'antd';
import { ReloadOutlined, WarningOutlined, PieChartOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { PageHeader } from '../components/common';
import { getAlertAnalysis } from '../api';
import type { AlertAnalysis } from '../types';

const AlertAnalysisPage: React.FC = () => {
  const [data, setData] = useState<AlertAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await getAlertAnalysis({ days: 7 });
      setData(res.data.data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16, color: '#999' }}>加载告警分析数据...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Typography.Text type="danger">加载分析数据失败，请确认后端服务已启动</Typography.Text>
        <div style={{ marginTop: 16 }}>
          <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>重试</Button>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16, color: '#999' }}>加载告警分析数据...</div>
      </div>
    );
  }

  const hasData = data.total > 0;

  const ackRate = data.ackRate || 0;

  const sourcePieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { fontSize: 10 } },
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '45%'],
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 1 },
        label: { show: false },
        data: data.sourceDistribution.map((s) => ({ value: s.count, name: s.label })),
      },
    ],
  };

  const hours = Array.from({ length: 24 }, (_, i) => i);
  const hourData = hours.map((h) => {
    const found = data.peakHours.find((p) => p.hour === h);
    return found ? found.count : 0;
  });

  const peakHourOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 30, right: 10, top: 10, bottom: 20 },
    xAxis: { type: 'category', data: hours.map((h) => `${h}:00`), axisLabel: { fontSize: 9, rotate: 30 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'bar',
        data: hourData,
        itemStyle: { color: '#ff4d4f', borderRadius: [4, 4, 0, 0] },
      },
    ],
  };

  const topTypes = data.topAnomalyTypes.slice(0, 10);
  const topTypeOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 120, right: 30, top: 10, bottom: 20 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: {
      type: 'category',
      data: topTypes.map((t) => t.label).reverse(),
      axisLabel: { fontSize: 10 },
    },
    series: [
      {
        type: 'bar',
        data: topTypes.map((t) => t.count).reverse(),
        itemStyle: { color: '#722ed1', borderRadius: [0, 4, 4, 0] },
      },
    ],
  };

  return (
    <div>
      <PageHeader
        title="告警分析"
        subtitle="告警原因聚合分析与系统健康评估"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadData()}>
            刷新
          </Button>
        }
      />

      {!hasData && (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <PieChartOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
          <Typography.Paragraph type="secondary" style={{ marginTop: 16, fontSize: 16 }}>
            暂无告警数据可分析
          </Typography.Paragraph>
          <Typography.Text type="secondary">系统运行正常，当前用户暂无告警记录</Typography.Text>
        </div>
      )}

      {hasData && (
        <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <Typography.Title level={3} style={{ margin: 0, color: '#1677ff' }}>{data.total}</Typography.Title>
              <Typography.Text type="secondary">7日内告警总数</Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <Typography.Title level={3} style={{ margin: 0, color: '#faad14' }}>{data.acknowledged}</Typography.Title>
              <Typography.Text type="secondary">已确认</Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <Typography.Title level={3} style={{ margin: 0, color: ackRate >= 80 ? '#52c41a' : '#ff4d4f' }}>
                {ackRate}%
              </Typography.Title>
              <Typography.Text type="secondary">确认率</Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <WarningOutlined style={{ fontSize: 24, color: '#ff4d4f' }} />
              <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                标签 &gt; {topTypes[0]?.label || '-'}
              </Typography.Text>
              <Typography.Text type="secondary">最常见异常</Typography.Text>
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="来源模块分布" size="small">
            <ReactECharts option={sourcePieOption} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="告警峰值时段" size="small">
            <ReactECharts option={peakHourOption} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Top 异常类型" size="small">
            <ReactECharts option={topTypeOption} style={{ height: 280 }} />
          </Card>
        </Col>
      </Row>

      <Card title="异常类型排名" style={{ marginTop: 16 }}>
        <Table
          dataSource={data.topAnomalyTypes}
          rowKey="type"
          pagination={false}
          size="small"
          columns={[
            { title: '排名', key: 'rank', width: 60, render: (_: unknown, __: unknown, i: number) => i + 1 },
            { title: '异常类型', dataIndex: 'label', key: 'label' },
            {
              title: '数量', dataIndex: 'count', key: 'count', width: 100,
              render: (v: number) => <Tag color="blue">{v}</Tag>,
            },
            {
              title: '占比', key: 'pct', width: 150,
              render: (_: unknown, record: { count: number }) => {
                const pct = data.total > 0 ? Math.round((record.count / data.total) * 100) : 0;
                return <Progress percent={pct} size="small" />;
              },
            },
          ]}
        />
      </Card>
        </>
      )}
    </div>
  );
};

export default AlertAnalysisPage;
