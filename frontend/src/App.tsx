import React, { Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import Login from './pages/Login';
import Register from './pages/Register';
import { useAuthStore } from './store/authStore';

const AuthenticatedApp = React.lazy(() => import('./AuthenticatedApp'));

const theme = {
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 8,
    colorBgContainer: '#ffffff',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
};

const AppFallback: React.FC = () => (
  <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <Spin size="large" />
  </div>
);

const App: React.FC = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return (
    <ConfigProvider theme={theme} locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
          <Route path="/register" element={isAuthenticated ? <Navigate to="/" replace /> : <Register />} />
          <Route
            path="/*"
            element={
              <Suspense fallback={<AppFallback />}>
                <AuthenticatedApp />
              </Suspense>
            }
          />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
};

export default App;
