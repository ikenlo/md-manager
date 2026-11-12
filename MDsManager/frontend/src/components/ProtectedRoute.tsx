import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { selectIsAuthenticated, useAuthStore } from '../store/auth';

export default function ProtectedRoute() {
  const authed = useAuthStore(selectIsAuthenticated);
  const loc = useLocation();
  return authed ? <Outlet /> : <Navigate to="/login" replace state={{ from: loc.pathname }} />;
}
