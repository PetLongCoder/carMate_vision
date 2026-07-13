import React, { useCallback } from 'react';
import { message } from 'antd';
import { getWechatDeleteQrcode, pollWechatDelete } from '../../api/auth';
import WechatQrPanel from './WechatQrPanel';

interface WechatDeletePanelProps {
  onSuccess: () => void;
}

const WechatDeletePanel: React.FC<WechatDeletePanelProps> = ({ onSuccess }) => {
  const handlePoll = useCallback(
    (result: { status: string }) => {
      if (result.status === 'confirmed') {
        onSuccess();
        return 'stop' as const;
      }
      if (result.status === 'expired') {
        message.warning('二维码已过期，请刷新');
        return 'stop' as const;
      }
      return 'continue' as const;
    },
    [onSuccess],
  );

  return (
    <WechatQrPanel
      fetchQrcode={getWechatDeleteQrcode}
      pollStatus={pollWechatDelete}
      onPoll={handlePoll}
      topHint="请使用已绑定的微信扫码确认注销，操作不可恢复。"
      qrAlt="注销账号"
      qrSize={200}
      loadingPadding={32}
    />
  );
};

export default WechatDeletePanel;
