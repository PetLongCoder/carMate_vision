import React, { useMemo, useState } from 'react';
import { Button, Form, Input, Modal, Select, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { changePassword, sendSecureEmailCode, sendSecureSmsCode } from '../../api/auth';
import VerificationCodeInput from '../../components/auth/VerificationCodeInput';
import { confirmPasswordRules, passwordFormRules } from '../../utils/validation';
import PasswordStrengthIndicator from '../../components/auth/PasswordStrengthIndicator';
import { resolveLoginMethods } from '../../utils/loginMethods';
import type { User, VerifyMethod } from '../../types';

interface ProfilePasswordModalProps {
  open: boolean;
  profile: User;
  onClose: () => void;
  onSuccess: (user: User) => void;
}

const ProfilePasswordModal: React.FC<ProfilePasswordModalProps> = ({ open, profile, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const verifyOptions = useMemo(() => {
    const methods = resolveLoginMethods(profile);
    const options: Array<{ value: VerifyMethod; label: string }> = [];
    if (methods.includes('password')) options.push({ value: 'password', label: '账号密码' });
    if (profile.phone) options.push({ value: 'phone', label: '手机号验证码' });
    if (profile.email) options.push({ value: 'email', label: '邮箱验证码' });
    return options;
  }, [profile]);

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  const handleSubmit = async (values: {
    verify_method: VerifyMethod;
    old_password?: string;
    code?: string;
    new_password: string;
  }) => {
    setLoading(true);
    try {
      onSuccess(
        await changePassword({
          verify_method: values.verify_method,
          old_password: values.old_password,
          code: values.code,
          new_password: values.new_password,
        }),
      );
      message.success('密码已修改');
      handleClose();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '修改密码失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="修改密码" open={open} onCancel={handleClose} footer={null} destroyOnHidden>
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{ verify_method: verifyOptions[0]?.value }}
      >
        <Form.Item name="verify_method" label="验证方式" rules={[{ required: true }]}>
          <Select options={verifyOptions} />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.verify_method !== cur.verify_method}>
          {({ getFieldValue }) =>
            getFieldValue('verify_method') === 'password' ? (
              <Form.Item name="old_password" label="原密码" rules={[{ required: true, message: '请输入原密码' }]}>
                <Input.Password prefix={<LockOutlined />} />
              </Form.Item>
            ) : (
              <Form.Item name="code" label="验证码" rules={[{ required: true, len: 6 }]}>
                <VerificationCodeInput
                  onSend={async () => {
                    const method = form.getFieldValue('verify_method');
                    if (method === 'phone') {
                      await sendSecureSmsCode('change_password');
                      message.success('验证码已发送（请在后端终端查看）');
                    } else {
                      const tip = await sendSecureEmailCode('change_password');
                      message.success(tip);
                    }
                  }}
                />
              </Form.Item>
            )
          }
        </Form.Item>
        <Form.Item label="新密码" required style={{ marginBottom: 0 }}>
          <Form.Item name="new_password" rules={passwordFormRules(true)} style={{ marginBottom: 8 }}>
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.new_password !== cur.new_password}>
            {({ getFieldValue }) => (
              <PasswordStrengthIndicator password={getFieldValue('new_password') || ''} />
            )}
          </Form.Item>
        </Form.Item>
        <Form.Item
          name="confirm_password"
          label="确认新密码"
          dependencies={['new_password']}
          rules={confirmPasswordRules('new_password', '新密码')}
        >
          <Input.Password prefix={<LockOutlined />} />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block>
          确认修改
        </Button>
      </Form>
    </Modal>
  );
};

export default ProfilePasswordModal;
