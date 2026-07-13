import React from 'react';
import {
  getWechatBindQrcode,
  getWechatRebindQrcode,
  getWechatUnbindQrcode,
  pollWechatBind,
  pollWechatRebind,
  pollWechatUnbind,
} from '../../api/auth';
import WechatActionModal from '../../components/auth/WechatActionModal';
import type { User } from '../../types';

export type WechatActionMode = 'bind' | 'unbind' | 'rebind';

interface ProfileWechatModalProps {
  action: WechatActionMode | null;
  onClose: () => void;
  onSuccess: (user: User) => void;
}

const ProfileWechatModal: React.FC<ProfileWechatModalProps> = ({ action, onClose, onSuccess }) => {
  if (!action) return null;

  return (
    <WechatActionModal
      action={action}
      open
      onClose={onClose}
      onSuccess={onSuccess}
      fetchQrcode={
        action === 'bind'
          ? getWechatBindQrcode
          : action === 'unbind'
            ? getWechatUnbindQrcode
            : getWechatRebindQrcode
      }
      pollStatus={
        action === 'bind' ? pollWechatBind : action === 'unbind' ? pollWechatUnbind : pollWechatRebind
      }
    />
  );
};

export default ProfileWechatModal;
