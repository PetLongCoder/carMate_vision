import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Modal, Typography, Spin, Button, message } from 'antd';
import { WechatOutlined, ReloadOutlined } from '@ant-design/icons';
import type { User, WechatBindPollResponse, WechatQrcodeResponse } from '../../types';

const { Text, Paragraph } = Typography;

type WechatAction = 'bind' | 'unbind' | 'rebind';

interface WechatActionModalProps {
  action: WechatAction;
  open: boolean;
  onClose: () => void;
  onSuccess: (user: User) => void;
  fetchQrcode: () => Promise<WechatQrcodeResponse>;
  pollStatus: (state: string) => Promise<WechatBindPollResponse>;
}

const titles: Record<WechatAction, string> = {
  bind: '绑定微信',
  unbind: '解绑微信',
  rebind: '换绑微信',
};

const WechatActionModal: React.FC<WechatActionModalProps> = ({
  action,
  open,
  onClose,
  onSuccess,
  fetchQrcode,
  pollStatus,
}) => {
  const [loading, setLoading] = useState(false);
  const [qrcode, setQrcode] = useState<WechatQrcodeResponse | null>(null);
  const [stepHint, setStepHint] = useState('');
  const pollTimerRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (state: string) => {
      stopPolling();
      pollTimerRef.current = window.setInterval(async () => {
        try {
          const result = await pollStatus(state);
          if (result.status === 'step1_done') {
            setStepHint('第一步已完成，请再次扫描二维码确认新微信');
            message.info('旧微信验证成功，请再次扫码');
            return;
          }
          if (result.status === 'confirmed' && result.user) {
            stopPolling();
            message.success(`${titles[action]}成功`);
            onSuccess(result.user);
            onClose();
          } else if (result.status === 'expired') {
            stopPolling();
            message.warning('二维码已过期，请刷新');
          }
        } catch {
          stopPolling();
        }
      }, 2000);
    },
    [action, onClose, onSuccess, pollStatus, stopPolling],
  );

  const loadQrcode = useCallback(async () => {
    setLoading(true);
    stopPolling();
    setStepHint('');
    try {
      const data = await fetchQrcode();
      setQrcode(data);
      if (action === 'rebind') {
        setStepHint(data.step === 1 ? '第一步：确认当前绑定的微信' : '请再次扫码确认新微信');
      }
      startPolling(data.state);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取二维码失败');
      setQrcode(null);
    } finally {
      setLoading(false);
    }
  }, [action, fetchQrcode, startPolling, stopPolling]);

  useEffect(() => {
    if (open) {
      void loadQrcode();
    } else {
      stopPolling();
      setQrcode(null);
      setStepHint('');
    }
    return () => stopPolling();
  }, [open, loadQrcode, stopPolling]);

  return (
    <Modal
      title={
        <span>
          <WechatOutlined style={{ color: '#07c160', marginRight: 8 }} />
          {titles[action]}
        </span>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={420}
      destroyOnHidden
    >
      <div style={{ textAlign: 'center', padding: '8px 0 4px' }}>
        {loading ? (
          <div style={{ padding: '48px 0' }}>
            <Spin size="large" />
          </div>
        ) : qrcode ? (
          <>
            <img
              src={`data:image/png;base64,${qrcode.qrcode_base64}`}
              alt={titles[action]}
              style={{ width: 220, height: 220, borderRadius: 12, border: '1px solid #f0f0f0', padding: 8 }}
            />
            {stepHint && (
              <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                {stepHint}
              </Paragraph>
            )}
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 12, lineHeight: 1.8 }}>
              {qrcode.network_hint}
            </Text>
            <Button icon={<ReloadOutlined />} onClick={() => void loadQrcode()} style={{ marginTop: 16 }}>
              刷新二维码
            </Button>
          </>
        ) : (
          <Button type="primary" onClick={() => void loadQrcode()}>
            重新获取二维码
          </Button>
        )}
      </div>
    </Modal>
  );
};

export default WechatActionModal;
