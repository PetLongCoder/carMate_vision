import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic } from 'antd';
import { CameraOutlined, AimOutlined, AlertOutlined, CarOutlined } from '@ant-design/icons';
import { PageHeader, Loading } from '../components/common';
import type { DashboardStats as StatsType } from '../types';

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<StatsType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // TODO: 接入真实 API
    const timer = setTimeout(() => {
      setStats({ totalPlates: 128, totalGestures: 56, totalAlerts: 12, unreadAlerts: 3 });
      setLoading(false);
    }, 600);
    return () => clearTimeout(timer);
  }, []);

  if (loading) return <Loading />;

  return (
    <div>
      <PageHeader title="控制面板" subtitle="CarMate 智能车载视觉系统总览" />

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="车牌识别总数" value={stats?.totalPlates} prefix={<CameraOutlined />} valueStyle={{ color: '#1677ff' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="手势识别总数" value={stats?.totalGestures} prefix={<AimOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="告警总数" value={stats?.totalAlerts} prefix={<AlertOutlined />} valueStyle={{ color: '#faad14' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="未读告警" value={stats?.unreadAlerts} prefix={<CarOutlined />} valueStyle={{ color: stats?.unreadAlerts ? '#ff4d4f' : '#52c41a' }} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        {[
          { path: '/plate', icon: <CameraOutlined style={{ fontSize: 48, color: '#fff' }} />, bg: 'linear-gradient(135deg, #1677ff 0%, #69b1ff 100%)', title: '车牌识别', desc: '上传图片或开启摄像头，自动识别车牌号码与颜色' },
          { path: '/police-gesture', icon: <AimOutlined style={{ fontSize: 48, color: '#fff' }} />, bg: 'linear-gradient(135deg, #722ed1 0%, #b37feb 100%)', title: '交警手势识别', desc: '识别交警8种手势信号，辅助安全驾驶决策' },
          { path: '/driver-gesture', icon: <CarOutlined style={{ fontSize: 48, color: '#fff' }} />, bg: 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)', title: '车主手势控车', desc: '识别车主手势，实现隔空控制车载设备' },
          { path: '/alerts', icon: <AlertOutlined style={{ fontSize: 48, color: '#fff' }} />, bg: 'linear-gradient(135deg, #fa541c 0%, #ff9c6e 100%)', title: '告警中心', desc: '实时监控系统日志，接收智能告警推送' },
        ].map((item) => (
          <Col xs={24} sm={12} lg={6} key={item.path}>
            <Card hoverable onClick={() => (window.location.href = item.path)}
              cover={<div style={{ height: 120, background: item.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{item.icon}</div>}>
              <Card.Meta title={item.title} description={item.desc} />
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
};

export default Dashboard;
