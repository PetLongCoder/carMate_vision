import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import AuthGuard from './components/auth/AuthGuard';
import RoleGuard from './components/auth/RoleGuard';
import Dashboard from './pages/Dashboard';
import PlateRecognition from './pages/PlateRecognition';
import PoliceGesture from './pages/PoliceGesture';
import DriverGesture from './pages/DriverGesture';
import AlertCenter from './pages/AlertCenter';
import AlertTimeline from './pages/AlertTimeline';
import AlertDetail from './pages/AlertDetail';
import UserOperationLogs from './pages/UserOperationLogs';
import AdminRecognitionRecords from './pages/AdminRecognitionRecords';
import History from './pages/History';
import Profile from './pages/Profile';
import { useWebSocket } from './hooks/useWebSocket';
import { useAuthStore } from './store/authStore';

const AlertDashboard = React.lazy(() => import('./pages/AlertDashboard'));
const AlertAnalysis = React.lazy(() => import('./pages/AlertAnalysis'));
const DashboardGestureStats = React.lazy(() => import('./pages/DashboardGestureStats'));

const PageFallback: React.FC = () => (
  <div style={{ padding: 48, textAlign: 'center' }}>加载中...</div>
);

const HomePage: React.FC = () => {
  const isAdmin = useAuthStore((s) => s.isAdmin());
  if (isAdmin) {
    return <Dashboard />;
  }
  return <Navigate to="/plate" replace />;
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
          <Route path="/profile" element={<Profile />} />
          <Route
            path="/alerts/dashboard"
            element={
              <React.Suspense fallback={<PageFallback />}>
                <AlertDashboard />
              </React.Suspense>
            }
          />
          <Route path="/alerts/timeline" element={<AlertTimeline />} />
          <Route path="/alerts/detail/:id" element={<AlertDetail />} />
          <Route
            path="/alerts/analysis"
            element={
              <React.Suspense fallback={<PageFallback />}>
                <AlertAnalysis />
              </React.Suspense>
            }
          />
          <Route element={<RoleGuard allowedRoles={['admin']} />}>
            <Route
              path="/dashboard/gestures"
              element={
                <React.Suspense fallback={<PageFallback />}>
                  <DashboardGestureStats />
                </React.Suspense>
              }
            />
            <Route path="/alerts" element={<AlertCenter />} />
            <Route path="/admin/operation-logs" element={<UserOperationLogs />} />
            <Route path="/admin/recognition-records" element={<AdminRecognitionRecords />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export default AuthenticatedApp;
