import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AppLayout from './components/layout/AppLayout';
import Dashboard from './pages/Dashboard';
import PlateRecognition from './pages/PlateRecognition';
import PoliceGesture from './pages/PoliceGesture';
import DriverGesture from './pages/DriverGesture';
import AlertCenter from './pages/AlertCenter';
import History from './pages/History';
import { useWebSocket } from './hooks/useWebSocket';

// Ant Design 主题配置
const theme = {
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 8,
    colorBgContainer: '#ffffff',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
};

const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/plate" element={<PlateRecognition />} />
      <Route path="/police-gesture" element={<PoliceGesture />} />
      <Route path="/driver-gesture" element={<DriverGesture />} />
      <Route path="/alerts" element={<AlertCenter />} />
      <Route path="/history" element={<History />} />
    </Routes>
  );
};

const App: React.FC = () => {
  // 初始化 WebSocket 连接（用于实时告警推送）
  useWebSocket();

  return (
    <ConfigProvider theme={theme} locale={zhCN}>
      <BrowserRouter>
        <AppLayout>
          <AppRoutes />
        </AppLayout>
      </BrowserRouter>
    </ConfigProvider>
  );
};

export default App;
