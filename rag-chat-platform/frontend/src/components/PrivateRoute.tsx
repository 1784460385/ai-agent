import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export function PrivateRoute() {
  const { user, ready } = useAuth();
  if (!ready) {
    return <div className="grid h-screen place-items-center text-sm text-slate-400">正在确认登录状态</div>;
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function AdminRoute() {
  const { user } = useAuth();
  if (user?.role !== 'admin') return <Navigate to="/chat" replace />;
  return <Outlet />;
}
