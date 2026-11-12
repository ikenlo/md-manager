import { BarChart3, Bot, CalendarDays, Megaphone, Users } from 'lucide-react';
import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AuthProvider from './components/AuthProvider';
import ProtectedRoute from './components/ProtectedRoute';
import { ToastContainer } from './components/ui';
import AppShell from './layout/AppShell';
import InboxPage from './pages/InboxPage';
import LoginPage from './pages/LoginPage';
import MorePage from './pages/MorePage';
import SectionPage from './pages/SectionPage';
import SettingsPage from './pages/SettingsPage';

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
          <Route element={<AppShell />}>
            <Route path="/" element={<InboxPage />} />
            <Route
              path="/appointments"
              element={
                <SectionPage
                  title="Записи"
                  sub="Календар записів салону"
                  icon={CalendarDays}
                  phase="Фаза 4"
                  planned={[
                    'Записи з MDS Connect: майстри, послуги, час',
                    'Записи, створені AI після вашого схвалення',
                    'Вільні вікна для швидкої відповіді клієнту',
                  ]}
                />
              }
            />
            <Route
              path="/clients"
              element={
                <SectionPage
                  title="Клієнти"
                  sub="Картки клієнтів і історія"
                  icon={Users}
                  phase="Фаза 4"
                  planned={[
                    'Картка клієнта: контакти, Instagram, телефон',
                    'Історія діалогів і візитів з MDS Connect',
                    'Джерела клієнтів і мітки',
                  ]}
                />
              }
            />
            <Route
              path="/agents"
              element={
                <SectionPage
                  title="AI-агенти"
                  sub="Налаштування AI-адміністратора"
                  icon={Bot}
                  phase="Фаза 4"
                  planned={[
                    'Тон і правила AI без редагування файлів',
                    'Режим за замовчуванням для нових діалогів',
                    'Статистика: скільки пропозицій схвалено й відхилено',
                  ]}
                />
              }
            />
            <Route
              path="/marketing"
              element={
                <SectionPage
                  title="Реклама"
                  sub="Кампанії Meta"
                  icon={Megaphone}
                  phase="Фаза 6"
                  planned={['Кампанії Instagram і Facebook', 'Бюджет і результати', 'Звідки приходять клієнти']}
                />
              }
            />
            <Route
              path="/analytics"
              element={
                <SectionPage
                  title="Аналітика"
                  sub="Воронка і звіти"
                  icon={BarChart3}
                  phase="Фаза 5"
                  planned={[
                    'Воронка: повідомлення → запис → візит',
                    'Швидкість відповіді адміністраторів і AI',
                    'Щоденний звіт: вчора проти середнього за тиждень',
                  ]}
                />
              }
            />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/more" element={<MorePage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ToastContainer />
    </AuthProvider>
  );
}
