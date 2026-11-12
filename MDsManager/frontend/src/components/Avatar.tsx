import { initials } from '../lib/format';

const TONES = [
  'bg-gold-tint text-gold',
  'bg-[#e3ece7] text-brand-2',
  'bg-[#efe7e1] text-[#8a5a44]',
  'bg-[#e6e8ef] text-[#4a5578]',
];

export default function Avatar({ name, size = 'md' }: { name: string; size?: 'md' | 'lg' }) {
  const tone = TONES[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % TONES.length];
  const dim = size === 'lg' ? 'h-12 w-12 text-base' : 'h-11 w-11 text-sm';
  return (
    <div className={`${dim} ${tone} flex shrink-0 items-center justify-center rounded-full font-bold`}>
      {initials(name)}
    </div>
  );
}
