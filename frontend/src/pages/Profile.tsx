import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Avatar,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  UserOutlined,
  MobileOutlined,
  MailOutlined,
  WechatOutlined,
  EditOutlined,
  LockOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  bindEmail,
  bindPhone,
  changePassword,
  deleteAccount,
  getCurrentUser,
  getWechatBindQrcode,
  getWechatRebindQrcode,
  getWechatUnbindQrcode,
  pollWechatBind,
  pollWechatRebind,
  pollWechatUnbind,
  rebindEmail,
  rebindPhone,
  sendEmailCode,
  sendSecureEmailCode,
  sendSecureSmsCode,
  sendSmsCode,
  unbindEmail,
  unbindPhone,
  updateProfile,
} from '../api/auth';
import VerificationCodeInput from '../components/auth/VerificationCodeInput';
import EmailInput from '../components/auth/EmailInput';
import WechatActionModal from '../components/auth/WechatActionModal';
import WechatDeletePanel from '../components/auth/WechatDeletePanel';
import { useAuthStore } from '../store/authStore';
import { emailFormRules, passwordFormRules, confirmPasswordRules, PASSWORD_HINT } from '../utils/validation';
import { resolveLoginMethods } from '../utils/loginMethods';
import type { User, VerifyMethod } from '../types';

const { Title, Text } = Typography;

const methodLabels: Record<string, string> = {
  password: '账号密码',
  phone: '手机号',
  email: '邮箱',
  wechat: '微信',
};

const Profile: React.FC = () => {
  const navigate = useNavigate();
  const { updateUser, logout } = useAuthStore();
  const [profile, setProfile] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [nicknameEditing, setNicknameEditing] = useState(false);
  const [nicknameLoading, setNicknameLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [phoneModal, setPhoneModal] = useState<'bind' | 'unbind' | 'rebind' | null>(null);
  const [emailModal, setEmailModal] = useState<'bind' | 'unbind' | 'rebind' | null>(null);
  const [wechatAction, setWechatAction] = useState<'bind' | 'unbind' | 'rebind' | null>(null);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [nicknameForm] = Form.useForm();
  const [phoneForm] = Form.useForm();
  const [emailForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [deleteForm] = Form.useForm();

  const applyUser = (user: User) => {
    setProfile(user);
    updateUser(user);
  };

  const loadProfile = useCallback(async () => {
    setLoading(true);
    try {
      const user = await getCurrentUser();
      applyUser(user);
      nicknameForm.setFieldsValue({ nickname: user.nickname || '' });
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载用户信息失败');
    } finally {
      setLoading(false);
    }
  }, [nicknameForm, updateUser]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const handleSaveNickname = async (values: { nickname: string }) => {
    setNicknameLoading(true);
    try {
      applyUser(await updateProfile({ nickname: values.nickname.trim() || undefined }));
      setNicknameEditing(false);
      message.success('昵称已更新');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '更新昵称失败');
    } finally {
      setNicknameLoading(false);
    }
  };

  const closePhoneModal = () => {
    setPhoneModal(null);
    phoneForm.resetFields();
  };

  const closeEmailModal = () => {
    setEmailModal(null);
    emailForm.resetFields();
  };

  const handlePhoneSubmit = async (values: Record<string, string>) => {
    setActionLoading(true);
    try {
      if (phoneModal === 'bind') {
        applyUser(await bindPhone({ phone: values.phone, code: values.code }));
        message.success('手机号绑定成功');
      } else if (phoneModal === 'unbind') {
        applyUser(await unbindPhone({ code: values.code }));
        message.success('手机号已解绑');
      } else if (phoneModal === 'rebind') {
        applyUser(
          await rebindPhone({
            old_code: values.old_code,
            new_phone: values.new_phone,
            new_code: values.new_code,
          }),
        );
        message.success('手机号换绑成功');
      }
      closePhoneModal();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleEmailSubmit = async (values: Record<string, string>) => {
    setActionLoading(true);
    try {
      if (emailModal === 'bind') {
        applyUser(await bindEmail({ email: values.email, code: values.code }));
        message.success('邮箱绑定成功');
      } else if (emailModal === 'unbind') {
        applyUser(await unbindEmail({ code: values.code }));
        message.success('邮箱已解绑');
      } else if (emailModal === 'rebind') {
        applyUser(
          await rebindEmail({
            old_code: values.old_code,
            new_email: values.new_email,
            new_code: values.new_code,
          }),
        );
        message.success('邮箱换绑成功');
      }
      closeEmailModal();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteAccount = async (values: { verify_method: VerifyMethod; password?: string; code?: string }) => {
    setActionLoading(true);
    try {
      await deleteAccount(values);
      message.success('账号已注销');
      logout();
      navigate('/login', { replace: true });
    } catch (err) {
      message.error(err instanceof Error ? err.message : '注销失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleChangePassword = async (values: {
    verify_method: VerifyMethod;
    old_password?: string;
    code?: string;
    new_password: string;
  }) => {
    setActionLoading(true);
    try {
      applyUser(
        await changePassword({
          verify_method: values.verify_method,
          old_password: values.old_password,
          code: values.code,
          new_password: values.new_password,
        }),
      );
      message.success('密码已修改');
      setPasswordOpen(false);
      passwordForm.resetFields();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '修改密码失败');
    } finally {
      setActionLoading(false);
    }
  };

  const verifyOptions = useMemo(() => {
    if (!profile) return [];
    const methods = resolveLoginMethods(profile);
    const options: Array<{ value: VerifyMethod; label: string }> = [];
    if (methods.includes('password')) options.push({ value: 'password', label: '账号密码' });
    if (profile.phone) options.push({ value: 'phone', label: '手机号验证码' });
    if (profile.email) options.push({ value: 'email', label: '邮箱验证码' });
    if (profile.has_wechat) options.push({ value: 'wechat', label: '微信扫码' });
    return options;
  }, [profile]);

  if (!profile && loading) return <Card loading />;
  if (!profile) return <Card>无法加载用户信息</Card>;

  const handleWechatDeleteSuccess = () => {
    message.success('账号已注销');
    setDeleteOpen(false);
    logout();
    navigate('/login', { replace: true });
  };

  const loginMethods = resolveLoginMethods(profile);
  const methodCount = loginMethods.length;

  const renderActions = (
    bound: boolean,
    onBind: () => void,
    onUnbind: () => void,
    onRebind: () => void,
  ) => (
    <Space wrap>
      {!bound && (
        <Button type="link" onClick={onBind}>
          绑定
        </Button>
      )}
      {bound && methodCount >= 2 && (
        <Button type="link" danger onClick={onUnbind}>
          解绑
        </Button>
      )}
      {bound && methodCount === 1 && (
        <Button type="link" onClick={onRebind}>
          换绑
        </Button>
      )}
    </Space>
  );

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <Title level={3} style={{ marginBottom: 24 }}>
        用户信息
      </Title>

      <Card loading={loading}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
          <Avatar size={72} src={profile.avatar_url} icon={<UserOutlined />} style={{ backgroundColor: '#1677ff' }} />
          <div>
            <Space align="center" style={{ marginBottom: 8 }}>
              <Title level={4} style={{ margin: 0 }}>
                {profile.nickname || profile.username}
              </Title>
              <Tag color={profile.role === 'admin' ? 'gold' : 'blue'}>
                {profile.role === 'admin' ? '管理员' : '普通用户'}
              </Tag>
            </Space>
            <Text type="secondary">用户名：{profile.username}</Text>
            <div style={{ marginTop: 8 }}>
              {loginMethods.map((m) => (
                <Tag key={m} style={{ marginBottom: 4 }}>
                  {methodLabels[m] || m}
                </Tag>
              ))}
            </div>
          </div>
        </div>

        <Descriptions column={1} bordered size="middle">
          <Descriptions.Item label="昵称">
            {nicknameEditing ? (
              <Form form={nicknameForm} layout="inline" onFinish={handleSaveNickname}>
                <Form.Item name="nickname" rules={[{ max: 20, message: '昵称不超过 20 字' }]}>
                  <Input placeholder="请输入昵称" maxLength={20} style={{ width: 220 }} />
                </Form.Item>
                <Form.Item>
                  <Space>
                    <Button type="primary" htmlType="submit" loading={nicknameLoading}>
                      保存
                    </Button>
                    <Button onClick={() => setNicknameEditing(false)}>取消</Button>
                  </Space>
                </Form.Item>
              </Form>
            ) : (
              <Space>
                <span>{profile.nickname || '未填写'}</span>
                <Button type="link" icon={<EditOutlined />} onClick={() => setNicknameEditing(true)}>
                  编辑
                </Button>
              </Space>
            )}
          </Descriptions.Item>

          <Descriptions.Item label="手机号">
            <Space direction="vertical" size={4}>
              {profile.phone ? (
                <Space>
                  <MobileOutlined />
                  {profile.phone}
                </Space>
              ) : (
                <Tag color="orange">未绑定</Tag>
              )}
              {renderActions(!!profile.phone, () => setPhoneModal('bind'), () => setPhoneModal('unbind'), () => setPhoneModal('rebind'))}
            </Space>
          </Descriptions.Item>

          <Descriptions.Item label="邮箱">
            <Space direction="vertical" size={4}>
              {profile.email ? (
                <Space>
                  <MailOutlined />
                  {profile.email}
                </Space>
              ) : (
                <Tag color="orange">未绑定</Tag>
              )}
              {renderActions(!!profile.email, () => setEmailModal('bind'), () => setEmailModal('unbind'), () => setEmailModal('rebind'))}
            </Space>
          </Descriptions.Item>

          <Descriptions.Item label="微信">
            <Space direction="vertical" size={4}>
              {profile.has_wechat ? (
                <Space>
                  <WechatOutlined style={{ color: '#07c160' }} />
                  <Tag color="success">已绑定</Tag>
                </Space>
              ) : (
                <Tag color="orange">未绑定</Tag>
              )}
              {renderActions(
                !!profile.has_wechat,
                () => setWechatAction('bind'),
                () => setWechatAction('unbind'),
                () => setWechatAction('rebind'),
              )}
            </Space>
          </Descriptions.Item>

          {loginMethods.includes('password') && (
            <Descriptions.Item label="账号密码">
              <Space>
                <LockOutlined />
                <Text type="secondary">已启用（用户名 + 密码登录）</Text>
                <Button type="link" onClick={() => setPasswordOpen(true)}>
                  修改密码
                </Button>
              </Space>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Card title="危险操作" style={{ marginTop: 16 }} bordered>
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          注销账号后数据无法恢复，请谨慎操作。注销前需验证身份。
        </Text>
        <Button danger icon={<DeleteOutlined />} onClick={() => setDeleteOpen(true)}>
          注销账号
        </Button>
      </Card>

      <Modal
        title={phoneModal === 'bind' ? '绑定手机号' : phoneModal === 'unbind' ? '解绑手机号' : '换绑手机号'}
        open={phoneModal !== null}
        onCancel={closePhoneModal}
        footer={null}
        destroyOnHidden
      >
        <Form form={phoneForm} layout="vertical" onFinish={handlePhoneSubmit}>
          {phoneModal === 'bind' && (
            <>
              <Form.Item name="phone" label="新手机号" rules={[{ required: true, pattern: /^1[3-9]\d{9}$/, message: '请输入正确手机号' }]}>
                <Input prefix={<MobileOutlined />} maxLength={11} />
              </Form.Item>
              <Form.Item name="code" label="验证码" rules={[{ required: true, len: 6 }]}>
                <VerificationCodeInput
                  onSend={async () => {
                    const phone = phoneForm.getFieldValue('phone');
                    await phoneForm.validateFields(['phone']);
                    await sendSmsCode({ phone, scene: 'bind' });
                    message.success('验证码已发送（请在后端终端查看）');
                  }}
                />
              </Form.Item>
            </>
          )}
          {phoneModal === 'unbind' && (
            <Form.Item name="code" label="当前手机号验证码" rules={[{ required: true, len: 6 }]}>
              <VerificationCodeInput
                onSend={async () => {
                  await sendSecureSmsCode('unbind');
                  message.success('验证码已发送（请在后端终端查看）');
                }}
              />
            </Form.Item>
          )}
          {phoneModal === 'rebind' && (
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
                    const new_phone = phoneForm.getFieldValue('new_phone');
                    await phoneForm.validateFields(['new_phone']);
                    await sendSmsCode({ phone: new_phone, scene: 'rebind_new' });
                    message.success('新手机号验证码已发送');
                  }}
                />
              </Form.Item>
            </>
          )}
          <Button type="primary" htmlType="submit" loading={actionLoading} block>
            确认
          </Button>
        </Form>
      </Modal>

      <Modal
        title={emailModal === 'bind' ? '绑定邮箱' : emailModal === 'unbind' ? '解绑邮箱' : '换绑邮箱'}
        open={emailModal !== null}
        onCancel={closeEmailModal}
        footer={null}
        destroyOnHidden
      >
        <Form form={emailForm} layout="vertical" onFinish={handleEmailSubmit}>
          {emailModal === 'bind' && (
            <>
              <Form.Item name="email" label="新邮箱" rules={emailFormRules(true)}>
                <EmailInput placeholder="请输入邮箱" />
              </Form.Item>
              <Form.Item name="code" label="验证码" rules={[{ required: true, len: 6 }]}>
                <VerificationCodeInput
                  onSend={async () => {
                    const email = emailForm.getFieldValue('email');
                    await emailForm.validateFields(['email']);
                    const tip = await sendEmailCode({ email, scene: 'bind' });
                    message.success(tip);
                  }}
                />
              </Form.Item>
            </>
          )}
          {emailModal === 'unbind' && (
            <Form.Item name="code" label="当前邮箱验证码" rules={[{ required: true, len: 6 }]}>
              <VerificationCodeInput
                onSend={async () => {
                  const tip = await sendSecureEmailCode('unbind');
                  message.success(tip);
                }}
              />
            </Form.Item>
          )}
          {emailModal === 'rebind' && (
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
                    const new_email = emailForm.getFieldValue('new_email');
                    await emailForm.validateFields(['new_email']);
                    const tip = await sendEmailCode({ email: new_email, scene: 'rebind_new' });
                    message.success(tip);
                  }}
                />
              </Form.Item>
            </>
          )}
          <Button type="primary" htmlType="submit" loading={actionLoading} block>
            确认
          </Button>
        </Form>
      </Modal>

      <Modal
        title="修改密码"
        open={passwordOpen}
        onCancel={() => {
          setPasswordOpen(false);
          passwordForm.resetFields();
        }}
        footer={null}
        destroyOnHidden
      >
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={handleChangePassword}
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
                      const method = passwordForm.getFieldValue('verify_method');
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
          <Form.Item
            name="new_password"
            label="新密码"
            extra={PASSWORD_HINT}
            rules={passwordFormRules(true)}
          >
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
            rules={confirmPasswordRules('new_password', '新密码')}
          >
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={actionLoading} block>
            确认修改
          </Button>
        </Form>
      </Modal>

      <Modal
        title="注销账号"
        open={deleteOpen}
        onCancel={() => {
          setDeleteOpen(false);
          deleteForm.resetFields();
        }}
        footer={null}
        destroyOnHidden
      >
        <Form form={deleteForm} layout="vertical" onFinish={handleDeleteAccount} initialValues={{ verify_method: verifyOptions[0]?.value }}>
          <Form.Item name="verify_method" label="验证方式" rules={[{ required: true }]}>
            <Select options={verifyOptions} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.verify_method !== cur.verify_method}>
            {({ getFieldValue }) => {
              const method = getFieldValue('verify_method');
              if (method === 'wechat') {
                return <WechatDeletePanel onSuccess={handleWechatDeleteSuccess} />;
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
                <Button type="primary" danger htmlType="submit" loading={actionLoading} block>
                  确认注销
                </Button>
              )
            }
          </Form.Item>
        </Form>
      </Modal>

      {wechatAction && (
        <WechatActionModal
          action={wechatAction}
          open={wechatAction !== null}
          onClose={() => setWechatAction(null)}
          onSuccess={applyUser}
          fetchQrcode={
            wechatAction === 'bind'
              ? getWechatBindQrcode
              : wechatAction === 'unbind'
                ? getWechatUnbindQrcode
                : getWechatRebindQrcode
          }
          pollStatus={
            wechatAction === 'bind'
              ? pollWechatBind
              : wechatAction === 'unbind'
                ? pollWechatUnbind
                : pollWechatRebind
          }
        />
      )}
    </div>
  );
};

export default Profile;
