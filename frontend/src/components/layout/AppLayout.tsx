import React from 'react';
import { Layout, Menu, Button, Badge, Tooltip } from 'antd';
import {
  CarOutlined,
  CameraOutlined,
  HighlightOutlined,
  AimOutlined,
  AlertOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppStore } from '../../store';

const { Sider, Content } = Layout;

const menuItems = [
  { key: '/', icon: <CarOutlined />, label: '控制面板' },
  { key: '/plate', icon: <CameraOutlined />, label: '车牌识别' },
  { key: '/police-gesture', icon: <HighlightOutlined />, label: '交警手势' },
  { key: '/driver-gesture', icon: <AimOutlined />, label: '车主手势' },
  { key: '/alerts', icon: <AlertOutlined />, label: '告警中心' },
  { key: '/history', icon: <HistoryOutlined />, label: '历史记录' },
];

const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar, unreadCount } = useAppStore();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 侧边栏 */}
      <Sider
        trigger={null}
        collapsible
        collapsed={sidebarCollapsed}
        width={220}
        style={{
          background: '#001529',
          borderRight: '1px solid rgba(255,255,255,0.06)',
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
          }}
        >
          <CarOutlined style={{ fontSize: 28, color: '#1677ff' }} />
          {!sidebarCollapsed && (
            <span style={{ color: '#fff', fontSize: 20, fontWeight: 700, marginLeft: 10, whiteSpace: 'nowrap' }}>
              CarMate
            </span>
          )}
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems.map((item) => ({
            ...item,
            label: item.key === '/alerts' && unreadCount > 0 ? (
              <span>
                {item.label}
                <Badge count={unreadCount} size="small" style={{ marginLeft: 8 }} />
              </span>
            ) : item.label,
          }))}
          onClick={({ key }) => navigate(key)}
          style={{ borderInlineEnd: 'none' }}
        />
      </Sider>

      {/* 主区域 */}
      <Layout>
        {/* 顶部栏 */}
        <div
          style={{
            height: 64,
            background: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
            borderBottom: '1px solid #f0f0f0',
            boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
          }}
        >
          <Button
            type="text"
            icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggleSidebar}
            style={{ fontSize: 16, width: 40, height: 40 }}
          />

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Tooltip title="告警通知">
              <Badge count={unreadCount} size="small">
                <BellOutlined style={{ fontSize: 18, cursor: 'pointer' }} onClick={() => navigate('/alerts')} />
              </Badge>
            </Tooltip>
            <span style={{ color: '#666', fontSize: 14 }}>
              CarMate 智能车载视觉系统
            </span>
          </div>
        </div>

        {/* 内容区 */}
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: '#fff',
            borderRadius: 8,
            minHeight: 'calc(100vh - 112px)',
            overflow: 'auto',
          }}
        >
          {children}
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
