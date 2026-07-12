import React, { useState } from 'react';
import { Card, Form, Input, Button, message, Typography, Divider, Row, Col } from 'antd';
import {
  LockOutlined,
  UserOutlined,
  MailOutlined,
  CarOutlined,
  MobileOutlined,
  SafetyCertificateOutlined,
  IdcardOutlined,
} from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { register, sendSmsCode } from '../api/auth';
import { useAuthStore } from '../store/authStore';
import VerificationCodeInput from '../components/auth/VerificationCodeInput';
import { emailFormRules } from '../utils/validation';
import { notifyAuthError } from '../utils/notifyAuthError';

const { Title, Text } = Typography;

const sectionTitleStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginBottom: 16,
  fontWeight: 600,
  color: '#1f2937',
};

const Register: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const smsSentHint =
    import.meta.env.DEV
      ? import.meta.env.VITE_USE_MOCK_AUTH !== 'false'
        ? '验证码已发送（开发环境请按 F12 在 Console 查看）'
        : '验证码已发送（请在后端终端查看验证码）'
      : '验证码已发送';

  const handleSendSmsCode = async () => {
    try {
      const phone = form.getFieldValue('phone');
      await form.validateFields(['phone']);
      await sendSmsCode({ phone, scene: 'register' });
      message.success(smsSentHint);
    } catch (err) {
      notifyAuthError(err, navigate);
    }
  };

  const handleSubmit = async (values: {
    username: string;
    phone: string;
    code: string;
    password: string;
    confirmPassword: string;
    email?: string;
  }) => {
    setLoading(true);
    try {
      const result = await register({
        username: values.username,
        phone: values.phone,
        code: values.code,
        password: values.password,
        email: values.email?.trim() || undefined,
      });

      setAuth(result.token, result.user);
      message.success('注册成功，已自动登录');
      navigate('/plate', { replace: true });
    } catch (err) {
      notifyAuthError(err, navigate);
    } finally {
      setLoading(false);
    }
  };

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
      <Card
        style={{
          width: '100%',
          maxWidth: 760,
          borderRadius: 12,
          boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
        }}
        styles={{ body: { padding: '28px 32px 24px' } }}
      >
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <CarOutlined style={{ fontSize: 40, color: '#1677ff' }} />
          <Title level={3} style={{ margin: '12px 0 4px' }}>
            创建 CarMate 账号
          </Title>
          <Text type="secondary">填写以下信息，一步完成注册</Text>
        </div>

        <Form form={form} layout="vertical" autoComplete="off" onFinish={handleSubmit}>
          <Row gutter={[32, 0]}>
            <Col xs={24} md={11}>
              <div style={sectionTitleStyle}>
                <SafetyCertificateOutlined style={{ color: '#1677ff' }} />
                <span>手机验证</span>
              </div>

              <Form.Item
                name="phone"
                label="手机号"
                rules={[
                  { required: true, message: '请输入手机号' },
                  { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号' },
                ]}
              >
                <Input
                  prefix={<MobileOutlined />}
                  placeholder="请输入手机号"
                  size="large"
                  maxLength={11}
                />
              </Form.Item>

              <Form.Item
                name="code"
                label="短信验证码"
                rules={[
                  { required: true, message: '请输入验证码' },
                  { len: 6, message: '验证码为 6 位数字' },
                ]}
              >
                <VerificationCodeInput onSend={handleSendSmsCode} />
              </Form.Item>

              <div
                style={{
                  padding: '12px 14px',
                  background: '#f0f5ff',
                  borderRadius: 8,
                  fontSize: 12,
                  color: '#597ef7',
                  lineHeight: 1.7,
                }}
              >
                手机号用于登录与安全验证，注册前请先获取并填写短信验证码。
              </div>
            </Col>

            <Col xs={0} md={2} style={{ display: 'flex', justifyContent: 'center' }}>
              <Divider type="vertical" style={{ height: '100%', minHeight: 280, margin: 0 }} />
            </Col>

            <Col xs={24} md={0}>
              <Divider style={{ margin: '8px 0 20px' }} />
            </Col>

            <Col xs={24} md={11}>
              <div style={sectionTitleStyle}>
                <IdcardOutlined style={{ color: '#1677ff' }} />
                <span>账号信息</span>
              </div>

              <Form.Item
                name="username"
                label="用户名"
                rules={[
                  { required: true, message: '请输入用户名' },
                  { min: 3, message: '用户名至少 3 个字符' },
                ]}
              >
                <Input prefix={<UserOutlined />} placeholder="请输入用户名" size="large" />
              </Form.Item>

              <Form.Item
                name="email"
                label="邮箱（可选）"
                extra="填写后可使用邮箱验证码登录"
                rules={emailFormRules(false)}
              >
                <Input prefix={<MailOutlined />} placeholder="请输入邮箱" size="large" />
              </Form.Item>

              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item
                    name="password"
                    label="密码"
                    rules={[
                      { required: true, message: '请输入密码' },
                      { min: 6, message: '密码至少 6 位' },
                    ]}
                  >
                    <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="confirmPassword"
                    label="确认密码"
                    dependencies={['password']}
                    rules={[
                      { required: true, message: '请再次输入密码' },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue('password') === value) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error('两次密码不一致'));
                        },
                      }),
                    ]}
                  >
                    <Input.Password prefix={<LockOutlined />} placeholder="确认密码" size="large" />
                  </Form.Item>
                </Col>
              </Row>
            </Col>
          </Row>

          <Form.Item style={{ marginTop: 8, marginBottom: 12 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              立即注册
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Text type="secondary">已有账号？</Text>{' '}
          <Link to="/login">返回登录</Link>
        </div>

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
            <div>注册需先获取手机验证码（Console 查看）</div>
            <div>用户名不可与 admin 重复；手机号不可与已有账号重复</div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default Register;
