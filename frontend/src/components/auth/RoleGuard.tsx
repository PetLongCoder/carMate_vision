import React from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Result, Button } from 'antd';
import { useAuthStore } from '../../store/authStore';
import type { UserRole } from '../../types';

interface RoleGuardProps {
  allowedRoles: UserRole[];
}

const RoleGuard: React.FC<RoleGuardProps> = ({ allowedRoles }) => {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  if (!user || !allowedRoles.includes(user.role)) {
    return (
      <Result
        status="403"
        title="无访问权限"
        subTitle="当前账号无权访问此页面，请联系管理员。"
        extra={
          <Button type="primary" onClick={() => navigate('/')}>
            返回首页
          </Button>
        }
      />
    );
  }

  return <Outlet />;
};

export default RoleGuard;
