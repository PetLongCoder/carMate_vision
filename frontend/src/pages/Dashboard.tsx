import React, { useCallback, useEffect, useState } from 'react';
import { Card, Row, Col, Button, Segmented, Statistic, message } from 'antd';
import {
  CameraOutlined,
  AimOutlined,
  AlertOutlined,
  ReloadOutlined,
  DashboardOutlined,
  CheckCircleOutlined,
  RiseOutlined,
} from '@ant-design/icons';
import { PageHeader, Loading } from '../components/common';
import DashboardRecordTable from '../components/dashboard/DashboardRecordTable';
import DashboardPoliceLogsTable from '../components/dashboard/DashboardPoliceLogsTable';
import DashboardAlertsTable from '../components/dashboard/DashboardAlertsTable';
import { getDashboardStats } from '../api/stats';
import type { DashboardStats as StatsType, GestureBreakdown } from '../types';

type DashboardCategory = 'overview' | 'plate' | 'gesture' | 'alerts';
type GestureSubCategory = 'police' | 'driver' | 'logs';

const emptyBreakdown: GestureBreakdown = {
  policeGestureRecords: 0,
  driverGestureRecords: 0,
  policeGestureLogs: 0,
  policeGestureLogsSuccess: 0,
};

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<StatsType | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [category, setCategory] = useState<DashboardCategory>('overview');
  const [gestureSub, setGestureSub] = useState<GestureSubCategory>('police');
  const [alertSub, setAlertSub] = useState<'all' | 'unread'>('all');

  const loadStats = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    try {
      const data = await getDashboardStats();
      setStats(data);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载统计数据失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  if (loading) return <Loading tip="正在加载统计数据..." />;

  const breakdown = stats?.gestureBreakdown ?? emptyBreakdown;

  const renderOverview = () => (
    <Row gutter={[16, 16]}>
      <Col xs={12} sm={8} lg={4}>
        <Card>
          <Statistic
            title="车牌识别"
            value={stats?.totalPlates ?? 0}
            prefix={<CameraOutlined />}
            valueStyle={{ color: '#1677ff' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={8} lg={4}>
        <Card>
          <Statistic
            title="手势识别"
            value={stats?.totalGestures ?? 0}
            prefix={<AimOutlined />}
            valueStyle={{ color: '#52c41a' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={8} lg={4}>
        <Card>
          <Statistic
            title="今日手势"
            value={stats?.todayGestures ?? 0}
            prefix={<RiseOutlined />}
            valueStyle={{ color: '#722ed1' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={8} lg={4}>
        <Card>
          <Statistic
            title="手势成功"
            value={stats?.successGestures ?? 0}
            prefix={<CheckCircleOutlined />}
            valueStyle={{ color: '#13c2c2' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={8} lg={4}>
        <Card>
          <Statistic
            title="告警总数"
            value={stats?.totalAlerts ?? 0}
            prefix={<AlertOutlined />}
            valueStyle={{ color: '#faad14' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={8} lg={4}>
        <Card>
          <Statistic
            title="未读告警"
            value={stats?.unreadAlerts ?? 0}
            prefix={<AlertOutlined />}
            valueStyle={{ color: stats?.unreadAlerts ? '#ff4d4f' : '#52c41a' }}
          />
        </Card>
      </Col>
    </Row>
  );

  const renderPlate = () => (
    <Card
      title={
        <span>
          车牌识别 <span style={{ color: '#1677ff', fontWeight: 600 }}>{stats?.totalPlates ?? 0}</span>{' '}
          次
        </span>
      }
    >
      <DashboardRecordTable type="plate" />
    </Card>
  );

  const renderGesture = () => (
    <Card
      title="手势识别"
      extra={
        <span style={{ color: '#999', fontSize: 13 }}>
          总计 {stats?.totalGestures ?? 0} · 今日 {stats?.todayGestures ?? 0} · 成功{' '}
          {stats?.successGestures ?? 0}
        </span>
      }
    >
      <Segmented
        block
        style={{ marginBottom: 16 }}
        value={gestureSub}
        onChange={(v) => setGestureSub(v as GestureSubCategory)}
        options={[
          {
            label: `交警手势（识别历史） ${breakdown.policeGestureRecords}`,
            value: 'police',
          },
          {
            label: `车主手势（识别历史） ${breakdown.driverGestureRecords}`,
            value: 'driver',
          },
          {
            label: `推理日志 ${breakdown.policeGestureLogs}`,
            value: 'logs',
          },
        ]}
      />
      {gestureSub === 'police' && <DashboardRecordTable type="police_gesture" />}
      {gestureSub === 'driver' && <DashboardRecordTable type="driver_gesture" />}
      {gestureSub === 'logs' && <DashboardPoliceLogsTable />}
    </Card>
  );

  const renderAlerts = () => (
    <Card
      title={
        <span>
          告警{' '}
          <span style={{ color: '#faad14', fontWeight: 600 }}>{stats?.totalAlerts ?? 0}</span> 条
          {stats?.unreadAlerts ? (
            <span style={{ color: '#ff4d4f', marginLeft: 12, fontSize: 14 }}>
              未读 {stats.unreadAlerts}
            </span>
          ) : null}
        </span>
      }
    >
      <Segmented
        style={{ marginBottom: 16 }}
        value={alertSub}
        onChange={(v) => setAlertSub(v as 'all' | 'unread')}
        options={[
          { label: '全部告警', value: 'all' },
          { label: `未读告警 (${stats?.unreadAlerts ?? 0})`, value: 'unread' },
        ]}
      />
      <DashboardAlertsTable acknowledged={alertSub === 'unread' ? false : undefined} />
    </Card>
  );

  const panels: Record<DashboardCategory, React.ReactNode> = {
    overview: renderOverview(),
    plate: renderPlate(),
    gesture: renderGesture(),
    alerts: renderAlerts(),
  };

  return (
    <div>
      <PageHeader
        title="控制面板"
        subtitle="CarMate 智能车载视觉系统总览"
        extra={
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => void loadStats(true)}>
            刷新
          </Button>
        }
      />

      <Segmented
        block
        size="large"
        value={category}
        onChange={(v) => setCategory(v as DashboardCategory)}
        style={{ marginBottom: 24 }}
        options={[
          { label: '总览', value: 'overview', icon: <DashboardOutlined /> },
          { label: '车牌识别', value: 'plate', icon: <CameraOutlined /> },
          {
            label: '手势识别',
            value: 'gesture',
            icon: <AimOutlined />,
          },
          { label: '告警', value: 'alerts', icon: <AlertOutlined /> },
        ]}
      />

      {panels[category]}
    </div>
  );
};

export default Dashboard;
