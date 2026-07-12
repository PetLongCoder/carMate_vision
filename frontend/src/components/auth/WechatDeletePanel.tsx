import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Typography, Spin, Button, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getWechatDeleteQrcode, pollWechatDelete } from '../../api/auth';
import type { WechatQrcodeResponse } from '../../types';

const { Text, Paragraph } = Typography;

interface WechatDeletePanelProps {
  onSuccess: () => void;
}

const WechatDeletePanel: React.FC<WechatDeletePanelProps> = ({ onSuccess }) => {
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
          const result = await pollWechatDelete(state);
          if (result.status === 'confirmed') {
            stopPolling();
            onSuccess();
          } else if (result.status === 'expired') {
            stopPolling();
            message.warning('二维码已过期，请刷新');
          }
        } catch {
          stopPolling();
        }
      }, 2000);
    },
    [onSuccess, stopPolling],
  );

  const loadQrcode = useCallback(async () => {
    setLoading(true);
    stopPolling();
    try {
      const data = await getWechatDeleteQrcode();
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
    void loadQrcode();
    return () => stopPolling();
  }, [loadQrcode, stopPolling]);

  return (
    <div style={{ textAlign: 'center', padding: '8px 0' }}>
      <Paragraph type="secondary" style={{ marginBottom: 16 }}>
        请使用已绑定的微信扫码确认注销，操作不可恢复。
      </Paragraph>
      {loading ? (
        <div style={{ padding: '32px 0' }}>
          <Spin size="large" />
        </div>
      ) : qrcode ? (
        <>
          <img
            src={`data:image/png;base64,${qrcode.qrcode_base64}`}
            alt="注销账号"
            style={{ width: 200, height: 200, borderRadius: 12, border: '1px solid #f0f0f0', padding: 8 }}
          />
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
  );
};

export default WechatDeletePanel;
