import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Button, Segmented, Row, Col, Statistic, Typography, message } from 'antd';
import {
  AimOutlined,
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

const { Text, Paragraph } = Typography;

export type GestureStatsMode = 'total' | 'today' | 'success';
export type GestureStatsTab = 'police' | 'driver' | 'logs';

const modeMeta: Record<
  GestureStatsMode,
  { title: string; subtitle: string; statTitle: string; color: string }
> = {
  total: {
    title: '全部手势记录',
    subtitle: '累计写入识别记录表的手势数据（含摄像头逐帧、未识别成功）',
    statTitle: '记录累计',
    color: '#52c41a',
  },
  today: {
    title: '今日手势记录',
    subtitle: '今日新增的识别记录（同一统计口径，必不大于累计）',
    statTitle: '今日记录',
    color: '#722ed1',
  },
  success: {
    title: '识别成功记录',
    subtitle: '累计识别成功的次数（必不大于记录累计）',
    statTitle: '成功累计',
    color: '#13c2c2',
  },
};

const emptyBreakdown: GestureBreakdown = {
  policeRecords: 0,
  driverRecords: 0,
  policeRecordsSuccess: 0,
  driverRecordsSuccess: 0,
  policeInferenceLogs: 0,
  policeInferenceLogsSuccess: 0,
};

const emptyTodayBreakdown: TodayGestureBreakdown = {
  policeRecords: 0,
  driverRecords: 0,
  policeRecordsSuccess: 0,
  driverRecordsSuccess: 0,
  policeInferenceLogs: 0,
  policeInferenceLogsSuccess: 0,
};

function getTabCounts(
  mode: GestureStatsMode,
  breakdown: GestureBreakdown,
  todayBreakdown: TodayGestureBreakdown,
) {
  if (mode === 'today') {
    return {
      police: todayBreakdown.policeRecords,
      driver: todayBreakdown.driverRecords,
      logs: todayBreakdown.policeInferenceLogs,
    };
  }
  if (mode === 'success') {
    return {
      police: breakdown.policeRecordsSuccess,
      driver: breakdown.driverRecordsSuccess,
      logs: breakdown.policeInferenceLogsSuccess,
    };
  }
  return {
    police: breakdown.policeRecords,
    driver: breakdown.driverRecords,
    logs: breakdown.policeInferenceLogs,
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
    if (mode === 'today') return stats?.gestureRecordToday ?? 0;
    if (mode === 'success') return stats?.gestureRecordSuccess ?? 0;
    return stats?.gestureRecordTotal ?? 0;
  }, [mode, stats]);

  const setTab = (next: GestureStatsTab) => {
    setSearchParams({ mode, tab: next });
  };

  const tableFilters = useMemo<{
    success?: boolean;
    startDate?: string;
    endDate?: string;
  }>(() => {
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
        onBack={() => navigate('/')}
        extra={
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => void loadStats(true)}>
            刷新
          </Button>
        }
      />

      <Paragraph type="secondary" style={{ marginTop: -8, marginBottom: 16 }}>
        主指标均来自识别记录表：累计 {stats?.gestureRecordTotal ?? 0} · 今日{' '}
        {stats?.gestureRecordToday ?? 0} · 成功 {stats?.gestureRecordSuccess ?? 0}
        {stats && stats.gestureRecordTodaySuccess > 0
          ? `（今日成功 ${stats.gestureRecordTodaySuccess}）`
          : ''}
      </Paragraph>

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
            <Statistic
              title="交警推理日志"
              value={tabCounts.logs}
              valueStyle={{ fontSize: 20 }}
            />
          </Card>
        </Col>
      </Row>

      <Segmented
        block
        size="large"
        value={tab}
        onChange={(v) => setTab(v as GestureStatsTab)}
        style={{ marginBottom: 12 }}
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
      {tab === 'logs' && (
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          推理日志为交警模块的逐段/逐帧明细，不计入上方三项主指标，仅供排查参考。
        </Text>
      )}

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
