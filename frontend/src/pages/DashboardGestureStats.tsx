import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Button, Segmented, Row, Col, Statistic, message } from 'antd';
import {
  AimOutlined,
  ArrowLeftOutlined,
  ReloadOutlined,
  HighlightOutlined,
  CarOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { PageHeader, Loading } from '../components/common';
import DashboardRecordTable from '../components/dashboard/DashboardRecordTable';
import DashboardPoliceLogsTable from '../components/dashboard/DashboardPoliceLogsTable';
import { getDashboardStats } from '../api/stats';
import type { DashboardStats, GestureBreakdown, TodayGestureBreakdown } from '../types';
import { todayRange } from '../utils/dashboardNav';

export type GestureStatsMode = 'total' | 'today' | 'success';
export type GestureStatsTab = 'police' | 'driver' | 'logs';

const modeMeta: Record<
  GestureStatsMode,
  { title: string; subtitle: string; statTitle: string; color: string }
> = {
  total: {
    title: '手势识别明细',
    subtitle: '查看交警手势、车主手势及推理日志分类数据',
    statTitle: '识别总量',
    color: '#52c41a',
  },
  today: {
    title: '今日手势识别',
    subtitle: '查看今日各分类的手势识别记录',
    statTitle: '今日总量',
    color: '#722ed1',
  },
  success: {
    title: '手势识别成功',
    subtitle: '查看各分类中识别成功的记录',
    statTitle: '成功总量',
    color: '#13c2c2',
  },
};

const emptyBreakdown: GestureBreakdown = {
  policeGestureRecords: 0,
  driverGestureRecords: 0,
  policeGestureLogs: 0,
  policeGestureLogsSuccess: 0,
};

const emptyTodayBreakdown: TodayGestureBreakdown = {
  policeGestureRecords: 0,
  driverGestureRecords: 0,
  policeGestureLogs: 0,
};

function getTabCounts(
  mode: GestureStatsMode,
  breakdown: GestureBreakdown,
  todayBreakdown: TodayGestureBreakdown,
) {
  if (mode === 'today') {
    return {
      police: todayBreakdown.policeGestureRecords,
      driver: todayBreakdown.driverGestureRecords,
      logs: todayBreakdown.policeGestureLogs,
    };
  }
  if (mode === 'success') {
    return {
      police: breakdown.policeGestureRecords,
      driver: breakdown.driverGestureRecords,
      logs: breakdown.policeGestureLogsSuccess,
    };
  }
  return {
    police: breakdown.policeGestureRecords,
    driver: breakdown.driverGestureRecords,
    logs: breakdown.policeGestureLogs,
  };
}

const DashboardGestureStats: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const mode = (searchParams.get('mode') as GestureStatsMode) || 'total';
  const tab = (searchParams.get('tab') as GestureStatsTab) || 'police';

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadStats = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      setStats(await getDashboardStats());
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

  const breakdown = stats?.gestureBreakdown ?? emptyBreakdown;
  const todayBreakdown = stats?.todayGestureBreakdown ?? emptyTodayBreakdown;
  const tabCounts = getTabCounts(mode, breakdown, todayBreakdown);
  const meta = modeMeta[mode] ?? modeMeta.total;

  const totalValue = useMemo(() => {
    if (mode === 'today') return stats?.todayGestures ?? 0;
    if (mode === 'success') return stats?.successGestures ?? 0;
    return stats?.totalGestures ?? 0;
  }, [mode, stats]);

  const setTab = (next: GestureStatsTab) => {
    setSearchParams({ mode, tab: next });
  };

  const tableFilters = useMemo(() => {
    const success = mode === 'success' ? true : undefined;
    if (mode === 'today') {
      return { success, ...todayRange() };
    }
    return { success };
  }, [mode]);

  if (loading) return <Loading tip="正在加载手势数据..." />;

  return (
    <div>
      <PageHeader
        title={meta.title}
        subtitle={meta.subtitle}
        extra={
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => void loadStats(true)}>
            刷新
          </Button>
        }
      />

      <Button
        type="link"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/')}
        style={{ paddingLeft: 0, marginBottom: 16 }}
      >
        返回控制面板
      </Button>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title={meta.statTitle}
              value={totalValue}
              prefix={<AimOutlined />}
              valueStyle={{ color: meta.color }}
            />
          </Card>
        </Col>
        <Col xs={8} sm={5}>
          <Card size="small">
            <Statistic title="交警手势" value={tabCounts.police} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={8} sm={5}>
          <Card size="small">
            <Statistic title="车主手势" value={tabCounts.driver} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={8} sm={6}>
          <Card size="small">
            <Statistic title="推理日志" value={tabCounts.logs} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
      </Row>

      <Segmented
        block
        size="large"
        value={tab}
        onChange={(v) => setTab(v as GestureStatsTab)}
        style={{ marginBottom: 20 }}
        options={[
          {
            label: (
              <span>
                <HighlightOutlined style={{ marginRight: 6 }} />
                交警手势 ({tabCounts.police})
              </span>
            ),
            value: 'police',
          },
          {
            label: (
              <span>
                <CarOutlined style={{ marginRight: 6 }} />
                车主手势 ({tabCounts.driver})
              </span>
            ),
            value: 'driver',
          },
          {
            label: (
              <span>
                <FileTextOutlined style={{ marginRight: 6 }} />
                推理日志 ({tabCounts.logs})
              </span>
            ),
            value: 'logs',
          },
        ]}
      />

      <Card>
        {tab === 'police' && (
          <DashboardRecordTable
            type="police_gesture"
            success={tableFilters.success}
            startDate={tableFilters.startDate}
            endDate={tableFilters.endDate}
          />
        )}
        {tab === 'driver' && (
          <DashboardRecordTable
            type="driver_gesture"
            success={tableFilters.success}
            startDate={tableFilters.startDate}
            endDate={tableFilters.endDate}
          />
        )}
        {tab === 'logs' && (
          <DashboardPoliceLogsTable
            todayOnly={mode === 'today'}
            successOnly={mode === 'success'}
          />
        )}
      </Card>
    </div>
  );
};

export default DashboardGestureStats;
