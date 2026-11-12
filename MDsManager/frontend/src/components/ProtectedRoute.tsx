import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../store/auth';

export default function ProtectedRoute() {
  const token = useAuth((s) => s.token);
  const loc = useLocation();
  return token ? <Outlet /> : <Navigate to="/login" replace state={{ from: loc.pathname }} />;
}
