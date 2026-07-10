import React from 'react';
import { Card, Statistic } from 'antd';
import { RightOutlined } from '@ant-design/icons';

interface StatCardProps {
  title: string;
  value: number;
  prefix: React.ReactNode;
  valueStyle?: React.CSSProperties;
  onClick?: () => void;
}

const StatCard: React.FC<StatCardProps> = ({ title, value, prefix, valueStyle, onClick }) => (
  <Card
    hoverable={!!onClick}
    onClick={onClick}
    style={{
      cursor: onClick ? 'pointer' : 'default',
      transition: 'box-shadow 0.2s, transform 0.2s',
    }}
    styles={{ body: { position: 'relative' } }}
  >
    <Statistic title={title} value={value} prefix={prefix} valueStyle={valueStyle} />
    {onClick && (
      <RightOutlined
        style={{
          position: 'absolute',
          right: 16,
          top: '50%',
          transform: 'translateY(-50%)',
          color: '#bfbfbf',
          fontSize: 12,
        }}
      />
    )}
  </Card>
);

export default StatCard;
