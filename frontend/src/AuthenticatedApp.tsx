import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import AuthGuard from './components/auth/AuthGuard';
import RoleGuard from './components/auth/RoleGuard';
import { useWebSocket } from './hooks/useWebSocket';
import { useAuthStore } from './store/authStore';

const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const PlateRecognition = React.lazy(() => import('./pages/PlateRecognition'));
const PoliceGesture = React.lazy(() => import('./pages/PoliceGesture'));
const DriverGesture = React.lazy(() => import('./pages/DriverGesture'));
const AlertCenter = React.lazy(() => import('./pages/AlertCenter'));
const AlertTimeline = React.lazy(() => import('./pages/AlertTimeline'));
const AlertDetail = React.lazy(() => import('./pages/AlertDetail'));
const AlertDashboard = React.lazy(() => import('./pages/AlertDashboard'));
const AlertAnalysis = React.lazy(() => import('./pages/AlertAnalysis'));
const DashboardGestureStats = React.lazy(() => import('./pages/DashboardGestureStats'));
const UserOperationLogs = React.lazy(() => import('./pages/UserOperationLogs'));
const AdminRecognitionRecords = React.lazy(() => import('./pages/AdminRecognitionRecords'));
const History = React.lazy(() => import('./pages/History'));
const Profile = React.lazy(() => import('./pages/Profile'));

const PageFallback: React.FC = () => (
  <div style={{ padding: 48, textAlign: 'center' }}>加载中...</div>
);

const LazyPage: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <React.Suspense fallback={<PageFallback />}>{children}</React.Suspense>
);

const HomePage: React.FC = () => {
  const isAdmin = useAuthStore((s) => s.isAdmin());
  if (isAdmin) {
    return (
      <LazyPage>
        <Dashboard />
      </LazyPage>
    );
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
          <Route path="/plate" element={<LazyPage><PlateRecognition /></LazyPage>} />
          <Route path="/police-gesture" element={<LazyPage><PoliceGesture /></LazyPage>} />
          <Route path="/driver-gesture" element={<LazyPage><DriverGesture /></LazyPage>} />
          <Route path="/history" element={<LazyPage><History /></LazyPage>} />
          <Route path="/profile" element={<LazyPage><Profile /></LazyPage>} />
          <Route path="/alerts/dashboard" element={<LazyPage><AlertDashboard /></LazyPage>} />
          <Route path="/alerts/timeline" element={<LazyPage><AlertTimeline /></LazyPage>} />
          <Route path="/alerts/detail/:id" element={<LazyPage><AlertDetail /></LazyPage>} />
          <Route path="/alerts/analysis" element={<LazyPage><AlertAnalysis /></LazyPage>} />
          <Route element={<RoleGuard allowedRoles={['admin']} />}>
            <Route path="/dashboard/gestures" element={<LazyPage><DashboardGestureStats /></LazyPage>} />
            <Route path="/alerts" element={<LazyPage><AlertCenter /></LazyPage>} />
            <Route path="/admin/operation-logs" element={<LazyPage><UserOperationLogs /></LazyPage>} />
            <Route path="/admin/recognition-records" element={<LazyPage><AdminRecognitionRecords /></LazyPage>} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export default AuthenticatedApp;
