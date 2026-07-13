import React, { useState } from 'react';
import { Button, Form, Modal, message } from 'antd';
import { bindEmail, rebindEmail, sendEmailCode, sendSecureEmailCode, unbindEmail } from '../../api/auth';
import VerificationCodeInput from '../../components/auth/VerificationCodeInput';
import EmailInput from '../../components/auth/EmailInput';
import { emailFormRules } from '../../utils/validation';
import type { User } from '../../types';

export type EmailModalMode = 'bind' | 'unbind' | 'rebind';

interface ProfileEmailModalProps {
  mode: EmailModalMode | null;
  onClose: () => void;
  onSuccess: (user: User) => void;
}

const titles: Record<EmailModalMode, string> = {
  bind: '绑定邮箱',
  unbind: '解绑邮箱',
  rebind: '换绑邮箱',
};

const ProfileEmailModal: React.FC<ProfileEmailModalProps> = ({ mode, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  const handleSubmit = async (values: Record<string, string>) => {
    if (!mode) return;
    setLoading(true);
    try {
      let user: User;
      if (mode === 'bind') {
        user = await bindEmail({ email: values.email, code: values.code });
        message.success('邮箱绑定成功');
      } else if (mode === 'unbind') {
        user = await unbindEmail({ code: values.code });
        message.success('邮箱已解绑');
      } else {
        user = await rebindEmail({
          old_code: values.old_code,
          new_email: values.new_email,
          new_code: values.new_code,
        });
        message.success('邮箱换绑成功');
      }
      onSuccess(user);
      handleClose();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={mode ? titles[mode] : ''} open={mode !== null} onCancel={handleClose} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={handleSubmit}>
        {mode === 'bind' && (
          <>
            <Form.Item name="email" label="新邮箱" rules={emailFormRules(true)}>
              <EmailInput placeholder="请输入邮箱" />
            </Form.Item>
            <Form.Item name="code" label="验证码" rules={[{ required: true, len: 6 }]}>
              <VerificationCodeInput
                onSend={async () => {
                  const email = form.getFieldValue('email');
                  await form.validateFields(['email']);
                  const tip = await sendEmailCode({ email, scene: 'bind' });
                  message.success(tip);
                }}
              />
            </Form.Item>
          </>
        )}
        {mode === 'unbind' && (
          <Form.Item name="code" label="当前邮箱验证码" rules={[{ required: true, len: 6 }]}>
            <VerificationCodeInput
              onSend={async () => {
                const tip = await sendSecureEmailCode('unbind');
                message.success(tip);
              }}
            />
          </Form.Item>
        )}
        {mode === 'rebind' && (
          <>
            <Form.Item name="old_code" label="原邮箱验证码" rules={[{ required: true, len: 6 }]}>
              <VerificationCodeInput
                onSend={async () => {
                  const tip = await sendSecureEmailCode('rebind_old');
                  message.success(tip);
                }}
              />
            </Form.Item>
            <Form.Item name="new_email" label="新邮箱" rules={emailFormRules(true)}>
              <EmailInput placeholder="请输入新邮箱" />
            </Form.Item>
            <Form.Item name="new_code" label="新邮箱验证码" rules={[{ required: true, len: 6 }]}>
              <VerificationCodeInput
                onSend={async () => {
                  const new_email = form.getFieldValue('new_email');
                  await form.validateFields(['new_email']);
                  const tip = await sendEmailCode({ email: new_email, scene: 'rebind_new' });
                  message.success(tip);
                }}
              />
            </Form.Item>
          </>
        )}
        <Button type="primary" htmlType="submit" loading={loading} block>
          确认
        </Button>
      </Form>
    </Modal>
  );
};

export default ProfileEmailModal;
