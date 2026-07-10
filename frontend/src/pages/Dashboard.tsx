import React, { useCallback, useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, Button, message } from 'antd';
import {
  CameraOutlined,
  AimOutlined,
  AlertOutlined,
  CarOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
  RiseOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { PageHeader, Loading } from '../components/common';
import { getDashboardStats } from '../api/stats';
import type { DashboardStats as StatsType } from '../types';

const shortcuts = [
  {
    path: '/plate',
    icon: <CameraOutlined style={{ fontSize: 48, color: '#fff' }} />,
    bg: 'linear-gradient(135deg, #1677ff 0%, #69b1ff 100%)',
    title: '车牌识别',
    desc: '上传图片或开启摄像头，自动识别车牌号码与颜色',
  },
  {
    path: '/police-gesture',
    icon: <AimOutlined style={{ fontSize: 48, color: '#fff' }} />,
    bg: 'linear-gradient(135deg, #722ed1 0%, #b37feb 100%)',
    title: '交警手势识别',
    desc: '识别交警8种手势信号，辅助安全驾驶决策',
  },
  {
    path: '/driver-gesture',
    icon: <CarOutlined style={{ fontSize: 48, color: '#fff' }} />,
    bg: 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)',
    title: '车主手势控车',
    desc: '识别车主手势，实现隔空控制车载设备',
  },
  {
    path: '/alerts',
    icon: <AlertOutlined style={{ fontSize: 48, color: '#fff' }} />,
    bg: 'linear-gradient(135deg, #fa541c 0%, #ff9c6e 100%)',
    title: '告警中心',
    desc: '实时监控系统日志，接收智能告警推送',
  },
  {
    path: '/admin/recognition-records',
    icon: <CameraOutlined style={{ fontSize: 48, color: '#fff' }} />,
    bg: 'linear-gradient(135deg, #08979c 0%, #5cdbd3 100%)',
    title: '识别记录管理',
    desc: '查看全部用户的识别记录，支持筛选与详情',
  },
  {
    path: '/admin/operation-logs',
    icon: <CheckCircleOutlined style={{ fontSize: 48, color: '#fff' }} />,
    bg: 'linear-gradient(135deg, #531dab 0%, #9254de 100%)',
    title: '用户操作日志',
    desc: '审计登录、注册、资料变更等账号操作',
  },
];

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<StatsType | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

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

  return (
    <div>
      <PageHeader
        title="控制面板"
        subtitle="CarMate 智能车载视觉系统总览（数据来自云数据库）"
        extra={
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => void loadStats(true)}>
            刷新
          </Button>
        }
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={8} lg={4}>
          <Card>
            <Statistic
              title="车牌识别总数"
              value={stats?.totalPlates ?? 0}
              prefix={<CameraOutlined />}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card>
            <Statistic
              title="手势识别总数"
              value={stats?.totalGestures ?? 0}
              prefix={<AimOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card>
            <Statistic
              title="今日手势识别"
              value={stats?.todayGestures ?? 0}
              prefix={<RiseOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card>
            <Statistic
              title="手势识别成功"
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
              prefix={<CarOutlined />}
              valueStyle={{ color: stats?.unreadAlerts ? '#ff4d4f' : '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        {shortcuts.map((item) => (
          <Col xs={24} sm={12} lg={8} key={item.path}>
            <Card
              hoverable
              onClick={() => navigate(item.path)}
              cover={
                <div
                  style={{
                    height: 120,
                    background: item.bg,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {item.icon}
                </div>
              }
            >
              <Card.Meta title={item.title} description={item.desc} />
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
};

export default Dashboard;
