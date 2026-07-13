import React, { useMemo, useState } from 'react';
import { Button, Form, Input, Modal, Select, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { deleteAccount, sendSecureEmailCode, sendSecureSmsCode } from '../../api/auth';
import VerificationCodeInput from '../../components/auth/VerificationCodeInput';
import WechatDeletePanel from '../../components/auth/WechatDeletePanel';
import { useAuthStore } from '../../store/authStore';
import { resolveLoginMethods } from '../../utils/loginMethods';
import type { User, VerifyMethod } from '../../types';

interface ProfileDeleteModalProps {
  open: boolean;
  profile: User;
  onClose: () => void;
}

const ProfileDeleteModal: React.FC<ProfileDeleteModalProps> = ({ open, profile, onClose }) => {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const verifyOptions = useMemo(() => {
    const methods = resolveLoginMethods(profile);
    const options: Array<{ value: VerifyMethod; label: string }> = [];
    if (methods.includes('password')) options.push({ value: 'password', label: '账号密码' });
    if (profile.phone) options.push({ value: 'phone', label: '手机号验证码' });
    if (profile.email) options.push({ value: 'email', label: '邮箱验证码' });
    if (profile.has_wechat) options.push({ value: 'wechat', label: '微信扫码' });
    return options;
  }, [profile]);

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  const finishDelete = () => {
    message.success('账号已注销');
    handleClose();
    logout();
    navigate('/login', { replace: true });
  };

  const handleSubmit = async (values: { verify_method: VerifyMethod; password?: string; code?: string }) => {
    setLoading(true);
    try {
      await deleteAccount(values);
      finishDelete();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '注销失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="注销账号" open={open} onCancel={handleClose} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ verify_method: verifyOptions[0]?.value }}>
        <Form.Item name="verify_method" label="验证方式" rules={[{ required: true }]}>
          <Select options={verifyOptions} />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.verify_method !== cur.verify_method}>
          {({ getFieldValue }) => {
            const method = getFieldValue('verify_method');
            if (method === 'wechat') {
              return <WechatDeletePanel onSuccess={finishDelete} />;
            }
            if (method === 'password') {
              return (
                <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                  <Input.Password prefix={<LockOutlined />} />
                </Form.Item>
              );
            }
            return (
              <Form.Item name="code" label="验证码" rules={[{ required: true, len: 6 }]}>
                <VerificationCodeInput
                  onSend={async () => {
                    if (method === 'phone') {
                      await sendSecureSmsCode('delete');
                      message.success('验证码已发送（请在后端终端查看）');
                    } else {
                      const tip = await sendSecureEmailCode('delete');
                      message.success(tip);
                    }
                  }}
                />
              </Form.Item>
            );
          }}
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.verify_method !== cur.verify_method}>
          {({ getFieldValue }) =>
            getFieldValue('verify_method') === 'wechat' ? null : (
              <Button type="primary" danger htmlType="submit" loading={loading} block>
                确认注销
              </Button>
            )
          }
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default ProfileDeleteModal;
