import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AppLayout from './components/layout/AppLayout';
import AuthGuard from './components/auth/AuthGuard';
import RoleGuard from './components/auth/RoleGuard';
import Dashboard from './pages/Dashboard';
import PlateRecognition from './pages/PlateRecognition';
import PoliceGesture from './pages/PoliceGesture';
import DriverGesture from './pages/DriverGesture';
import AlertCenter from './pages/AlertCenter';
import History from './pages/History';
import Login from './pages/Login';
import Register from './pages/Register';
import { useWebSocket } from './hooks/useWebSocket';
import { useAuthStore } from './store/authStore';

const theme = {
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 8,
    colorBgContainer: '#ffffff',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
};

const HomePage: React.FC = () => {
  const isAdmin = useAuthStore((s) => s.isAdmin());
  return isAdmin ? <Dashboard /> : <Navigate to="/plate" replace />;
};

const AuthenticatedApp: React.FC = () => {
  useWebSocket();
  return (
    <Routes>
      <Route element={<AuthGuard />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/plate" element={<PlateRecognition />} />
          <Route path="/police-gesture" element={<PoliceGesture />} />
          <Route path="/driver-gesture" element={<DriverGesture />} />
          <Route path="/history" element={<History />} />
          <Route element={<RoleGuard allowedRoles={['admin']} />}>
            <Route path="/alerts" element={<AlertCenter />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

const App: React.FC = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return (
    <ConfigProvider theme={theme} locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
          <Route path="/register" element={isAuthenticated ? <Navigate to="/" replace /> : <Register />} />
          <Route path="/*" element={<AuthenticatedApp />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
};

export default App;
