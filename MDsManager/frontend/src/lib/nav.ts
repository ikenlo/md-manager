import { BarChart3, Bot, CalendarDays, Megaphone, MessageCircle, Settings, Users, type LucideIcon } from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  group: string;
}

/** Розділи застосунку — як NAV у MDS Connect (групи в сайдбарі). */
export const NAV: NavItem[] = [
  { to: '/', label: 'Діалоги', icon: MessageCircle, group: 'Робота' },
  { to: '/appointments', label: 'Записи', icon: CalendarDays, group: 'Робота' },
  { to: '/clients', label: 'Клієнти', icon: Users, group: 'Робота' },
  { to: '/agents', label: 'AI-агенти', icon: Bot, group: 'AI' },
  { to: '/marketing', label: 'Реклама', icon: Megaphone, group: 'Маркетинг' },
  { to: '/analytics', label: 'Аналітика', icon: BarChart3, group: 'Маркетинг' },
  { to: '/settings', label: 'Налаштування', icon: Settings, group: 'Салон' },
];

/** Нижній таббар на телефоні (Connect MOBILE_TABS); решта — у «Меню». */
export const MOBILE_TABS = ['/', '/appointments', '/clients', '/more'];

export const ROLE_LABEL: Record<string, string> = {
  director: 'Директор',
  owner: 'Власник',
  admin: 'Адміністратор',
};

export function titleFor(pathname: string): string {
  if (pathname === '/more') return 'Меню';
  return NAV.find((n) => n.to === pathname)?.label ?? 'MDs Manager';
}
