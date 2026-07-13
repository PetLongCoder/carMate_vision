import React from 'react';
import { Typography, Spin, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { WechatQrcodeResponse } from '../../types';
import {
  useWechatQrcodePoll,
  type WechatQrPollHandlerResult,
  type WechatQrPollResult,
} from './useWechatQrcodePoll';

const { Text, Paragraph } = Typography;

export interface WechatQrPanelProps {
  active?: boolean;
  fetchQrcode: () => Promise<WechatQrcodeResponse>;
  pollStatus: (state: string) => Promise<WechatQrPollResult>;
  onPoll: (result: WechatQrPollResult) => WechatQrPollHandlerResult;
  onLoaded?: (data: WechatQrcodeResponse) => string | undefined;
  topHint?: React.ReactNode;
  qrAlt?: string;
  qrSize?: number;
  loadingPadding?: number;
}

const WechatQrPanel: React.FC<WechatQrPanelProps> = ({
  active = true,
  fetchQrcode,
  pollStatus,
  onPoll,
  onLoaded,
  topHint,
  qrAlt = '微信扫码',
  qrSize = 220,
  loadingPadding = 48,
}) => {
  const { loading, qrcode, hint, loadQrcode } = useWechatQrcodePoll({
    active,
    fetchQrcode,
    pollStatus,
    onPoll,
    onLoaded,
  });

  return (
    <div style={{ textAlign: 'center', padding: '8px 0 4px' }}>
      {topHint && (
        <Paragraph type="secondary" style={{ marginBottom: 16 }}>
          {topHint}
        </Paragraph>
      )}
      {loading ? (
        <div style={{ padding: `${loadingPadding}px 0` }}>
          <Spin size="large" />
        </div>
      ) : qrcode ? (
        <>
          <img
            src={`data:image/png;base64,${qrcode.qrcode_base64}`}
            alt={qrAlt}
            style={{
              width: qrSize,
              height: qrSize,
              borderRadius: 12,
              border: '1px solid #f0f0f0',
              padding: 8,
            }}
          />
          {hint && (
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              {hint}
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
  );
};

export default WechatQrPanel;
