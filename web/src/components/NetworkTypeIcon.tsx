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
  lan: 'text-emerald-600 dark:text-emerald-400',
  wan: 'text-[#0f62fe] dark:text-info',
  wifi: 'text-[#1192e8] dark:text-info',
  sfp: 'text-[#8a3ffc] dark:text-accent',
  console: 'text-muted-foreground',
  bmc: 'text-[#da1e28] dark:text-destructive-foreground',
  mgmt: 'text-[#0072c3] dark:text-info',
  dmz: 'text-[#f1c21b] dark:text-warning',
  vlan: 'text-[#00856a] dark:text-success',
  vpn: 'text-[#6929c4] dark:text-accent',
  custom: 'text-muted-foreground',
};

export function NetworkTypeIcon({ type, className }: { type: string | null; className?: string }) {
  const slug = type || 'custom';
  const Icon = iconMap[slug] || iconMap.custom;
  const color = colorMap[slug] || colorMap.custom;
  return <Icon className={`h-4 w-4 ${color} ${className || ''}`} />;
}
