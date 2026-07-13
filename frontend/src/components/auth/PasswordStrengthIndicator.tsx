import React from 'react';
import { Progress, Space, Typography } from 'antd';
import { CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons';
import { analyzePasswordStrength, PASSWORD_HINT, type PasswordStrengthLevel } from '../../utils/validation';

const { Text } = Typography;

const STRENGTH_COLORS: Record<PasswordStrengthLevel, string> = {
  weak: '#ff4d4f',
  fair: '#faad14',
  good: '#1677ff',
  strong: '#52c41a',
};

interface PasswordStrengthIndicatorProps {
  password?: string;
}

const PasswordStrengthIndicator: React.FC<PasswordStrengthIndicatorProps> = ({ password = '' }) => {
  if (!password) {
    return (
      <Text type="secondary" style={{ fontSize: 12 }}>
        {PASSWORD_HINT}
      </Text>
    );
  }

  const strength = analyzePasswordStrength(password);

  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Progress
          percent={strength.percent}
          showInfo={false}
          strokeColor={STRENGTH_COLORS[strength.level]}
          size="small"
          style={{ flex: 1, margin: 0 }}
        />
        <Text style={{ fontSize: 12, color: STRENGTH_COLORS[strength.level], whiteSpace: 'nowrap' }}>
          {strength.label}
        </Text>
      </div>
      <Space direction="vertical" size={2}>
        {strength.checks.map((item) => (
          <Text
            key={item.key}
            style={{ fontSize: 12, color: item.passed ? '#52c41a' : '#8c8c8c' }}
          >
            {item.passed ? (
              <CheckCircleFilled style={{ marginRight: 6 }} />
            ) : (
              <CloseCircleFilled style={{ marginRight: 6, color: '#d9d9d9' }} />
            )}
            {item.label}
          </Text>
        ))}
      </Space>
    </div>
  );
};

export default PasswordStrengthIndicator;
