import React, { useState } from 'react';
import { Card, Form, Input, Button, Tabs, message, Typography } from 'antd';
import { LockOutlined, UserOutlined, CarOutlined, MobileOutlined, MailOutlined } from '@ant-design/icons';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { login, loginByPhone, loginByEmail, sendSmsCode, sendEmailCode } from '../api/auth';
import { useAuthStore } from '../store/authStore';
import VerificationCodeInput from '../components/auth/VerificationCodeInput';
import { emailFormRules } from '../utils/validation';
import { notifyAuthError } from '../utils/notifyAuthError';
import type { AuthResponse, UserRole } from '../types';

const { Title, Text } = Typography;

type LoginMethod = 'password' | 'phone' | 'email';

const Login: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [activeRole, setActiveRole] = useState<UserRole>('user');
  const [loginMethod, setLoginMethod] = useState<LoginMethod>('password');
  const [passwordForm] = Form.useForm();
  const [phoneForm] = Form.useForm();
  const [emailForm] = Form.useForm();
  const navigate = useNavigate();
  const location = useLocation();
  const setAuth = useAuthStore((s) => s.setAuth);

  const from = (location.state as { from?: string } | null)?.from || '/';

  const finishLogin = (result: AuthResponse) => {
    if (result.user.role !== activeRole) {
      message.error(activeRole === 'admin' ? '该账号不是管理员' : '请使用管理员登录入口');
      return;
    }

    setAuth(result.token, result.user);
    message.success('登录成功');

    const defaultHome = result.user.role === 'admin' ? '/' : '/plate';
    const adminOnlyPaths = ['/alerts'];
    const target =
      from.startsWith('/login') || adminOnlyPaths.includes(from) ? defaultHome : from;

    navigate(target, { replace: true });
  };

  const handlePasswordLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      finishLogin(await login(values));
    } catch (err) {
      notifyAuthError(err, navigate);
    } finally {
      setLoading(false);
    }
  };

  const handlePhoneLogin = async (values: { phone: string; code: string }) => {
    setLoading(true);
    try {
      finishLogin(await loginByPhone(values));
    } catch (err) {
      notifyAuthError(err, navigate);
    } finally {
      setLoading(false);
    }
  };

  const handleEmailLogin = async (values: { email: string; code: string }) => {
    setLoading(true);
    try {
      finishLogin(await loginByEmail(values));
    } catch (err) {
      notifyAuthError(err, navigate);
    } finally {
      setLoading(false);
    }
  };

  const handleSendSmsCode = async () => {
    try {
      const phone = phoneForm.getFieldValue('phone');
      await phoneForm.validateFields(['phone']);
      await sendSmsCode({ phone, scene: 'login' });
      message.success(
        import.meta.env.DEV
          ? '验证码已发送（开发环境请按 F12 在 Console 查看）'
          : '验证码已发送',
      );
    } catch (err) {
      notifyAuthError(err, navigate);
    }
  };

  const handleSendEmailCode = async () => {
    try {
      const email = emailForm.getFieldValue('email');
      await emailForm.validateFields(['email']);
      await sendEmailCode({ email, scene: 'login' });
      message.success(
        import.meta.env.DEV
          ? '验证码已发送（开发环境请按 F12 在 Console 查看）'
          : '验证码已发送',
      );
    } catch (err) {
      notifyAuthError(err, navigate);
    }
  };

  const roleTabItems = [
    { key: 'user', label: '普通用户登录' },
    { key: 'admin', label: '管理员登录' },
  ];

  const methodTabItems =
    activeRole === 'user'
      ? [
          { key: 'password', label: '账号密码' },
          { key: 'phone', label: '手机验证码' },
          { key: 'email', label: '邮箱验证码' },
        ]
      : [{ key: 'password', label: '账号密码' }];

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #001529 0%, #1677ff 100%)',
        padding: 24,
      }}
    >
      <Card style={{ width: 440, borderRadius: 12, boxShadow: '0 8px 32px rgba(0,0,0,0.2)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <CarOutlined style={{ fontSize: 40, color: '#1677ff' }} />
          <Title level={3} style={{ margin: '12px 0 4px' }}>
            CarMate 登录
          </Title>
          <Text type="secondary">智能车载视觉系统</Text>
        </div>

        <Tabs
          activeKey={activeRole}
          onChange={(key) => {
            setActiveRole(key as UserRole);
            setLoginMethod('password');
          }}
          items={roleTabItems}
          centered
          style={{ marginBottom: 8 }}
        />

        <Tabs
          activeKey={loginMethod}
          onChange={(key) => setLoginMethod(key as LoginMethod)}
          items={methodTabItems}
          centered
          size="small"
          style={{ marginBottom: 16 }}
        />

        {loginMethod === 'password' && (
          <Form form={passwordForm} layout="vertical" onFinish={handlePasswordLogin} autoComplete="off">
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="请输入用户名" size="large" />
            </Form.Item>

            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" size="large" />
            </Form.Item>

            <Form.Item style={{ marginBottom: 12 }}>
              <Button type="primary" htmlType="submit" loading={loading} block size="large">
                登录
              </Button>
            </Form.Item>
          </Form>
        )}

        {loginMethod === 'phone' && activeRole === 'user' && (
          <Form form={phoneForm} layout="vertical" onFinish={handlePhoneLogin} autoComplete="off">
            <Form.Item
              name="phone"
              label="手机号"
              rules={[
                { required: true, message: '请输入手机号' },
                { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号' },
              ]}
            >
              <Input prefix={<MobileOutlined />} placeholder="请输入手机号" size="large" maxLength={11} />
            </Form.Item>

            <Form.Item
              name="code"
              label="验证码"
              rules={[
                { required: true, message: '请输入验证码' },
                { len: 6, message: '验证码为 6 位数字' },
              ]}
            >
              <VerificationCodeInput onSend={handleSendSmsCode} />
            </Form.Item>

            <Form.Item style={{ marginBottom: 12 }}>
              <Button type="primary" htmlType="submit" loading={loading} block size="large">
                登录
              </Button>
            </Form.Item>
          </Form>
        )}

        {loginMethod === 'email' && activeRole === 'user' && (
          <Form form={emailForm} layout="vertical" onFinish={handleEmailLogin} autoComplete="off">
            <Form.Item
              name="email"
              label="邮箱"
              rules={emailFormRules(true)}
            >
              <Input prefix={<MailOutlined />} placeholder="请输入邮箱" size="large" />
            </Form.Item>

            <Form.Item
              name="code"
              label="验证码"
              rules={[
                { required: true, message: '请输入验证码' },
                { len: 6, message: '验证码为 6 位数字' },
              ]}
            >
              <VerificationCodeInput onSend={handleSendEmailCode} />
            </Form.Item>

            <Form.Item style={{ marginBottom: 12 }}>
              <Button type="primary" htmlType="submit" loading={loading} block size="large">
                登录
              </Button>
            </Form.Item>
          </Form>
        )}

        {activeRole === 'user' && (
          <div style={{ textAlign: 'center', marginTop: 12 }}>
            <Text type="secondary">还没有账号？</Text>{' '}
            <Link to="/register">立即注册</Link>
          </div>
        )}

        {import.meta.env.DEV && import.meta.env.VITE_USE_MOCK_AUTH !== 'false' && (
          <div
            style={{
              marginTop: 16,
              padding: 12,
              background: '#f6ffed',
              border: '1px solid #b7eb8f',
              borderRadius: 8,
              fontSize: 12,
              color: '#389e0d',
              lineHeight: 1.8,
            }}
          >
            <div>账号密码：user/123456，admin/123456</div>
            <div>手机验证码：13800138000（Console 查看验证码）</div>
            <div>邮箱验证码：user@example.com（Console 查看验证码）</div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default Login;
