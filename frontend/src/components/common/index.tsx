import React from 'react';
import { Spin, Empty as AntEmpty } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';

export const Loading: React.FC<{ tip?: string }> = ({ tip = '加载中...' }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 60,
      color: '#999',
    }}
  >
    <Spin indicator={<LoadingOutlined style={{ fontSize: 40 }} spin />} />
    <span style={{ marginTop: 16 }}>{tip}</span>
  </div>
);

export const Empty: React.FC<{ description?: string }> = ({ description = '暂无数据' }) => (
  <AntEmpty description={description} style={{ padding: 60 }} />
);

export const PageHeader: React.FC<{
  title: string;
  subtitle?: string;
  extra?: React.ReactNode;
}> = ({ title, subtitle, extra }) => (
  <div
    style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      marginBottom: 24,
      paddingBottom: 16,
      borderBottom: '1px solid #f0f0f0',
    }}
  >
    <div>
      <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>{title}</h1>
      {subtitle && <p style={{ margin: '4px 0 0', color: '#999', fontSize: 14 }}>{subtitle}</p>}
    </div>
    {extra && <div>{extra}</div>}
  </div>
);
