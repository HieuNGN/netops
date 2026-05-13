import { Globe, Wifi, Cable, Terminal, Server, Shield, Network, Layers, Lock, HelpCircle } from 'lucide-react';

const iconMap: Record<string, typeof Globe> = {
  lan: Network,
  wan: Globe,
  wifi: Wifi,
  sfp: Cable,
  console: Terminal,
  bmc: Server,
  mgmt: Server,
  dmz: Shield,
  vlan: Layers,
  vpn: Lock,
  custom: HelpCircle,
};

const colorMap: Record<string, string> = {
  lan: 'text-[#24a148] dark:text-[#42be65]',
  wan: 'text-[#0f62fe] dark:text-[#78a9ff]',
  wifi: 'text-[#1192e8] dark:text-[#82cfff]',
  sfp: 'text-[#8a3ffc] dark:text-[#be95ff]',
  console: 'text-[#525252] dark:text-[#a8a8a8]',
  bmc: 'text-[#da1e28] dark:text-[#ff8389]',
  mgmt: 'text-[#0072c3] dark:text-[#82cfff]',
  dmz: 'text-[#f1c21b] dark:text-[#fddc69]',
  vlan: 'text-[#00856a] dark:text-[#44e0c0]',
  vpn: 'text-[#6929c4] dark:text-[#be95ff]',
  custom: 'text-[#525252] dark:text-[#a8a8a8]',
};

export function NetworkTypeIcon({ type, className }: { type: string | null; className?: string }) {
  const slug = type || 'custom';
  const Icon = iconMap[slug] || iconMap.custom;
  const color = colorMap[slug] || colorMap.custom;
  return <Icon className={`h-4 w-4 ${color} ${className || ''}`} />;
}
