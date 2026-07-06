import React, { useState } from 'react';
import { Card, Form, Input, Button, message, Typography, Space } from 'antd';
import {
  LockOutlined,
  UserOutlined,
  MailOutlined,
  CarOutlined,
  MobileOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { register, sendSmsCode } from '../api/auth';
import { useAuthStore } from '../store/authStore';
import VerificationCodeInput from '../components/auth/VerificationCodeInput';
import { emailFormRules } from '../utils/validation';
import { notifyAuthError } from '../utils/notifyAuthError';

const { Title, Text } = Typography;

const STEP_PHONE = 0;
const STEP_ACCOUNT = 1;

const Register: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(STEP_PHONE);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const handleSendSmsCode = async () => {
    try {
      const phone = form.getFieldValue('phone');
      await form.validateFields(['phone']);
      await sendSmsCode({ phone, scene: 'register' });
      message.success(
        import.meta.env.DEV
          ? '验证码已发送（开发环境请按 F12 在 Console 查看）'
          : '验证码已发送',
      );
    } catch (err) {
      notifyAuthError(err, navigate);
    }
  };

  const handleNext = async () => {
    try {
      await form.validateFields(['phone', 'code']);
      setCurrentStep(STEP_ACCOUNT);
    } catch {
      message.warning('请先完成手机号验证');
    }
  };

  const handlePrev = () => {
    setCurrentStep(STEP_PHONE);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      const result = await register({
        username: values.username,
        phone: values.phone,
        code: values.code,
        password: values.password,
        email: values.email,
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
      <Card style={{ width: 460, borderRadius: 12, boxShadow: '0 8px 32px rgba(0,0,0,0.2)' }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <CarOutlined style={{ fontSize: 40, color: '#1677ff' }} />
          <Title level={3} style={{ margin: '12px 0 0' }}>
            用户注册
          </Title>
        </div>

        <Form form={form} layout="vertical" autoComplete="off" preserve>
          <div style={{ minHeight: 220 }}>
            {currentStep === STEP_PHONE && (
              <>
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
              </>
            )}

            {currentStep === STEP_ACCOUNT && (
              <>
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

                <Form.Item
                  name="password"
                  label="密码"
                  rules={[
                    { required: true, message: '请输入密码' },
                    { min: 6, message: '密码至少 6 位' },
                  ]}
                >
                  <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" size="large" />
                </Form.Item>

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
                        return Promise.reject(new Error('两次输入的密码不一致'));
                      },
                    }),
                  ]}
                >
                  <Input.Password
                    prefix={<LockOutlined />}
                    placeholder="请再次输入密码"
                    size="large"
                  />
                </Form.Item>
              </>
            )}
          </div>

          <Form.Item style={{ marginBottom: 12 }}>
            {currentStep === STEP_PHONE ? (
              <Button type="primary" block size="large" onClick={handleNext}>
                下一步
              </Button>
            ) : (
              <Space style={{ width: '100%' }} direction="vertical" size={12}>
                <Button type="primary" block size="large" loading={loading} onClick={handleSubmit}>
                  完成注册
                </Button>
                <Button block size="large" icon={<ArrowLeftOutlined />} onClick={handlePrev}>
                  上一步
                </Button>
              </Space>
            )}
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Text type="secondary">已有账号？</Text>{' '}
          <Link to="/login">返回登录</Link>
        </div>
      </Card>
    </div>
  );
};

export default Register;
