import React, { useEffect, useState } from 'react';
import { Button, Input, Space } from 'antd';

interface VerificationCodeInputProps {
  value?: string;
  onChange?: (value: string) => void;
  onSend: () => Promise<void>;
  placeholder?: string;
  countdown?: number;
}

const VerificationCodeInput: React.FC<VerificationCodeInputProps> = ({
  value,
  onChange,
  onSend,
  placeholder = '请输入验证码',
  countdown = 60,
}) => {
  const [seconds, setSeconds] = useState(0);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (seconds <= 0) return;
    const timer = window.setTimeout(() => setSeconds((s) => s - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [seconds]);

  const handleSend = async () => {
    setSending(true);
    try {
      await onSend();
      setSeconds(countdown);
    } finally {
      setSending(false);
    }
  };

  return (
    <Space.Compact style={{ width: '100%' }}>
      <Input
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        size="large"
        maxLength={6}
      />
      <Button size="large" disabled={seconds > 0} loading={sending} onClick={handleSend}>
        {seconds > 0 ? `${seconds}s 后重发` : '获取验证码'}
      </Button>
    </Space.Compact>
  );
};

export default VerificationCodeInput;
