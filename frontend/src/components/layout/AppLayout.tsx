import React, { useMemo } from 'react';
import { Layout, Menu, Button, Badge, Tooltip, Dropdown, Tag, Space } from 'antd';
import type { MenuProps } from 'antd';
import {
  CarOutlined,
  CameraOutlined,
  VideoCameraOutlined,
  HighlightOutlined,
  AimOutlined,
  AlertOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
  UserOutlined,
  LogoutOutlined,
  ProfileOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useAppStore } from '../../store';
import { useAuthStore } from '../../store/authStore';
import type { UserRole } from '../../types';

const { Sider, Content } = Layout;

const allMenuItems: Array<{
  key: string;
  icon: React.ReactNode;
  label: string;
  roles: UserRole[];
}> = [
  { key: '/', icon: <CarOutlined />, label: '控制面板', roles: ['admin'] },
  { key: '/plate', icon: <CameraOutlined />, label: '车牌识别', roles: ['user', 'admin'] },
  { key: '/stream', icon: <VideoCameraOutlined />, label: '实时流识别', roles: ['user', 'admin'] },
  { key: '/police-gesture', icon: <HighlightOutlined />, label: '交警手势', roles: ['user', 'admin'] },
  { key: '/driver-gesture', icon: <AimOutlined />, label: '车主手势', roles: ['user', 'admin'] },
  { key: '/alerts', icon: <AlertOutlined />, label: '告警中心', roles: ['admin'] },
  { key: '/history', icon: <HistoryOutlined />, label: '历史记录', roles: ['user', 'admin'] },
];

const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar, unreadCount } = useAppStore();
  const { user, logout, isAdmin } = useAuthStore();

  const menuItems = useMemo(
    () =>
      allMenuItems
        .filter((item) => user && item.roles.includes(user.role))
        .map((item) => ({
          key: item.key,
          icon: item.icon,
          label:
            item.key === '/alerts' && unreadCount > 0 ? (
              <span>
                {item.label}
                <Badge count={unreadCount} size="small" style={{ marginLeft: 8 }} />
              </span>
            ) : (
              item.label
            ),
        })),
    [user, unreadCount],
  );

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'profile',
      icon: <ProfileOutlined />,
      label: '用户信息',
      onClick: () => navigate('/profile'),
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: () => {
        logout();
        navigate('/login', { replace: true });
      },
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
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
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderInlineEnd: 'none' }}
        />
      </Sider>

      <Layout>
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
            {isAdmin() && (
              <Tooltip title="告警通知">
                <Badge count={unreadCount} size="small">
                  <BellOutlined
                    style={{ fontSize: 18, cursor: 'pointer' }}
                    onClick={() => navigate('/alerts')}
                  />
                </Badge>
              </Tooltip>
            )}

            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <UserOutlined />
                <span>{user?.username}</span>
                <Tag color={isAdmin() ? 'gold' : 'blue'}>{isAdmin() ? '管理员' : '普通用户'}</Tag>
              </Space>
            </Dropdown>
          </div>
        </div>

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
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
