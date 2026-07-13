import React, { useCallback, useEffect, useState } from 'react';
import {
  Avatar,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
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
import { getCurrentUser, updateProfile } from '../api/auth';
import { useAuthStore } from '../store/authStore';
import { resolveLoginMethods } from '../utils/loginMethods';
import type { User } from '../types';
import ProfilePhoneModal, { type PhoneModalMode } from './Profile/ProfilePhoneModal';
import ProfileEmailModal, { type EmailModalMode } from './Profile/ProfileEmailModal';
import ProfilePasswordModal from './Profile/ProfilePasswordModal';
import ProfileDeleteModal from './Profile/ProfileDeleteModal';
import ProfileWechatModal, { type WechatActionMode } from './Profile/ProfileWechatModal';

const { Title, Text } = Typography;

const methodLabels: Record<string, string> = {
  password: '账号密码',
  phone: '手机号',
  email: '邮箱',
  wechat: '微信',
};

const Profile: React.FC = () => {
  const { updateUser } = useAuthStore();
  const [profile, setProfile] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [nicknameEditing, setNicknameEditing] = useState(false);
  const [nicknameLoading, setNicknameLoading] = useState(false);
  const [phoneModal, setPhoneModal] = useState<PhoneModalMode | null>(null);
  const [emailModal, setEmailModal] = useState<EmailModalMode | null>(null);
  const [wechatAction, setWechatAction] = useState<WechatActionMode | null>(null);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [nicknameForm] = Form.useForm();

  const applyUser = useCallback(
    (user: User) => {
      setProfile(user);
      updateUser(user);
    },
    [updateUser],
  );

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
  }, [applyUser, nicknameForm]);

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

  if (!profile && loading) return <Card loading />;
  if (!profile) return <Card>无法加载用户信息</Card>;

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

      <ProfilePhoneModal mode={phoneModal} onClose={() => setPhoneModal(null)} onSuccess={applyUser} />
      <ProfileEmailModal mode={emailModal} onClose={() => setEmailModal(null)} onSuccess={applyUser} />
      <ProfilePasswordModal
        open={passwordOpen}
        profile={profile}
        onClose={() => setPasswordOpen(false)}
        onSuccess={applyUser}
      />
      <ProfileDeleteModal open={deleteOpen} profile={profile} onClose={() => setDeleteOpen(false)} />
      <ProfileWechatModal action={wechatAction} onClose={() => setWechatAction(null)} onSuccess={applyUser} />
    </div>
  );
};

export default Profile;
