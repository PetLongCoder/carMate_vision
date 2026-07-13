import React, { useState } from 'react';
import { Button, Form, Input, Modal, message } from 'antd';
import { MobileOutlined } from '@ant-design/icons';
import { bindPhone, rebindPhone, sendSecureSmsCode, sendSmsCode, unbindPhone } from '../../api/auth';
import VerificationCodeInput from '../../components/auth/VerificationCodeInput';
import type { User } from '../../types';

export type PhoneModalMode = 'bind' | 'unbind' | 'rebind';

interface ProfilePhoneModalProps {
  mode: PhoneModalMode | null;
  onClose: () => void;
  onSuccess: (user: User) => void;
}

const titles: Record<PhoneModalMode, string> = {
  bind: '绑定手机号',
  unbind: '解绑手机号',
  rebind: '换绑手机号',
};

const ProfilePhoneModal: React.FC<ProfilePhoneModalProps> = ({ mode, onClose, onSuccess }) => {
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
        user = await bindPhone({ phone: values.phone, code: values.code });
        message.success('手机号绑定成功');
      } else if (mode === 'unbind') {
        user = await unbindPhone({ code: values.code });
        message.success('手机号已解绑');
      } else {
        user = await rebindPhone({
          old_code: values.old_code,
          new_phone: values.new_phone,
          new_code: values.new_code,
        });
        message.success('手机号换绑成功');
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
            <Form.Item name="phone" label="新手机号" rules={[{ required: true, pattern: /^1[3-9]\d{9}$/, message: '请输入正确手机号' }]}>
              <Input prefix={<MobileOutlined />} maxLength={11} />
            </Form.Item>
            <Form.Item name="code" label="验证码" rules={[{ required: true, len: 6 }]}>
              <VerificationCodeInput
                onSend={async () => {
                  const phone = form.getFieldValue('phone');
                  await form.validateFields(['phone']);
                  await sendSmsCode({ phone, scene: 'bind' });
                  message.success('验证码已发送（请在后端终端查看）');
                }}
              />
            </Form.Item>
          </>
        )}
        {mode === 'unbind' && (
          <Form.Item name="code" label="当前手机号验证码" rules={[{ required: true, len: 6 }]}>
            <VerificationCodeInput
              onSend={async () => {
                await sendSecureSmsCode('unbind');
                message.success('验证码已发送（请在后端终端查看）');
              }}
            />
          </Form.Item>
        )}
        {mode === 'rebind' && (
          <>
            <Form.Item name="old_code" label="原手机号验证码" rules={[{ required: true, len: 6 }]}>
              <VerificationCodeInput
                onSend={async () => {
                  await sendSecureSmsCode('rebind_old');
                  message.success('原手机号验证码已发送');
                }}
              />
            </Form.Item>
            <Form.Item name="new_phone" label="新手机号" rules={[{ required: true, pattern: /^1[3-9]\d{9}$/, message: '请输入正确手机号' }]}>
              <Input prefix={<MobileOutlined />} maxLength={11} />
            </Form.Item>
            <Form.Item name="new_code" label="新手机号验证码" rules={[{ required: true, len: 6 }]}>
              <VerificationCodeInput
                onSend={async () => {
                  const new_phone = form.getFieldValue('new_phone');
                  await form.validateFields(['new_phone']);
                  await sendSmsCode({ phone: new_phone, scene: 'rebind_new' });
                  message.success('新手机号验证码已发送');
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

export default ProfilePhoneModal;
