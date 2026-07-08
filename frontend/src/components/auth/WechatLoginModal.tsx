import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Modal, Typography, Spin, Button, message } from 'antd';
import { WechatOutlined, ReloadOutlined } from '@ant-design/icons';
import { getWechatQrcode, pollWechatLogin } from '../../api/auth';
import type { AuthResponse, WechatQrcodeResponse } from '../../types';

const { Text, Paragraph } = Typography;

interface WechatLoginModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (result: AuthResponse) => void;
}

const WechatLoginModal: React.FC<WechatLoginModalProps> = ({ open, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [qrcode, setQrcode] = useState<WechatQrcodeResponse | null>(null);
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
          const result = await pollWechatLogin(state);
          if (result.status === 'confirmed' && result.auth) {
            stopPolling();
            message.success('微信扫码登录成功');
            onSuccess(result.auth);
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
    [onClose, onSuccess, stopPolling],
  );

  const loadQrcode = useCallback(async () => {
    setLoading(true);
    stopPolling();
    try {
      const data = await getWechatQrcode();
      setQrcode(data);
      startPolling(data.state);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取二维码失败');
      setQrcode(null);
    } finally {
      setLoading(false);
    }
  }, [startPolling, stopPolling]);

  useEffect(() => {
    if (open) {
      void loadQrcode();
    } else {
      stopPolling();
      setQrcode(null);
    }

    return () => {
      stopPolling();
    };
  }, [open, loadQrcode, stopPolling]);

  return (
    <Modal
      title={
        <span>
          <WechatOutlined style={{ color: '#07c160', marginRight: 8 }} />
          微信扫码登录
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
            <Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
              正在生成二维码...
            </Paragraph>
          </div>
        ) : qrcode ? (
          <>
            <img
              src={`data:image/png;base64,${qrcode.qrcode_base64}`}
              alt="微信扫码登录"
              style={{
                width: 220,
                height: 220,
                borderRadius: 12,
                border: '1px solid #f0f0f0',
                padding: 8,
                background: '#fff',
              }}
            />
            <Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 8 }}>
              请使用手机微信「扫一扫」扫描上方二维码
            </Paragraph>
            <div
              style={{
                marginTop: 8,
                padding: '10px 12px',
                background: '#f6ffed',
                border: '1px solid #b7eb8f',
                borderRadius: 8,
                textAlign: 'left',
              }}
            >
              <Text style={{ fontSize: 12, color: '#389e0d', display: 'block', lineHeight: 1.8 }}>
                已自动检测本机 IP：{qrcode.lan_ip}
                <br />
                后端默认端口 8000，同学 clone 后一般无需改 .env
                <br />
                扫不开时可改用手机热点，或让后端加 --host 0.0.0.0
              </Text>
            </div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', lineHeight: 1.8, marginTop: 12 }}>
              手机需与电脑连接同一 WiFi / 热点
              <br />
              扫码后在手机上点击「确认登录」
              <br />
              二维码 {Math.floor(qrcode.expires_in / 60)} 分钟内有效
            </Text>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => void loadQrcode()}
              style={{ marginTop: 16 }}
            >
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

export default WechatLoginModal;
