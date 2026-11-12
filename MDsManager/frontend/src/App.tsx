import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AuthProvider from './components/AuthProvider';
import ProtectedRoute from './components/ProtectedRoute';
import { ToastContainer } from './components/ui';
import InboxPage from './pages/InboxPage';
import LoginPage from './pages/LoginPage';

// UI kit лише для `npm run dev`: у production-збірці гілка відкидається разом з імпортом
const DemoPage = import.meta.env.DEV ? lazy(() => import('./pages/_DemoPage')) : null;

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/_demo"
          element={
            DemoPage ? (
              <Suspense fallback={null}>
                <DemoPage />
              </Suspense>
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<InboxPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ToastContainer />
    </AuthProvider>
  );
}
