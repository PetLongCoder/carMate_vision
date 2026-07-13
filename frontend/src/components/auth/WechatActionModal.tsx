import React, { useCallback } from 'react';
import { Modal, message } from 'antd';
import { WechatOutlined } from '@ant-design/icons';
import type { User, WechatBindPollResponse, WechatQrcodeResponse } from '../../types';
import WechatQrPanel from './WechatQrPanel';

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
  const handlePoll = useCallback(
    (result: WechatBindPollResponse) => {
      if (result.status === 'step1_done') {
        message.info('旧微信验证成功，请再次扫码');
        return {
          action: 'continue' as const,
          hint: '第一步已完成，请再次扫描二维码确认新微信',
        };
      }
      if (result.status === 'confirmed' && result.user) {
        message.success(`${titles[action]}成功`);
        onSuccess(result.user);
        onClose();
        return 'stop' as const;
      }
      if (result.status === 'expired') {
        message.warning('二维码已过期，请刷新');
        return 'stop' as const;
      }
      return 'continue' as const;
    },
    [action, onClose, onSuccess],
  );

  const handleLoaded = useCallback(
    (data: WechatQrcodeResponse) => {
      if (action !== 'rebind') return undefined;
      return data.step === 1 ? '第一步：确认当前绑定的微信' : '请再次扫码确认新微信';
    },
    [action],
  );

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
      <WechatQrPanel
        active={open}
        fetchQrcode={fetchQrcode}
        pollStatus={pollStatus}
        onPoll={handlePoll}
        onLoaded={handleLoaded}
        qrAlt={titles[action]}
      />
    </Modal>
  );
};

export default WechatActionModal;
