import { Facebook, Instagram, Send } from 'lucide-react';
import type { ChannelType } from '../types';

const META: Record<ChannelType, { Icon: typeof Send; cls: string; label: string }> = {
  instagram: { Icon: Instagram, cls: 'text-[#c13584]', label: 'Instagram' },
  telegram: { Icon: Send, cls: 'text-[#2aa3df]', label: 'Telegram' },
  facebook: { Icon: Facebook, cls: 'text-[#1877f2]', label: 'Facebook' },
};

export default function ChannelIcon({ type, size = 14 }: { type: ChannelType; size?: number }) {
  const { Icon, cls, label } = META[type];
  return <Icon size={size} className={cls} aria-label={label} strokeWidth={2.2} />;
}

export const channelLabel = (t: ChannelType) => META[t].label;
