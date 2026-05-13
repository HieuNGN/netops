export interface NetworkTypeDef {
  slug: string;
  label: string;
  description: string;
}

export const NETWORK_TYPES: NetworkTypeDef[] = [
  { slug: "lan", label: "LAN", description: "Wired local area network segment" },
  { slug: "wan", label: "WAN", description: "Wide area or uplink connection" },
  { slug: "wifi", label: "Wi-Fi", description: "Wireless LAN / 802.11" },
  { slug: "sfp", label: "SFP / Fiber", description: "Optical fiber via SFP/SFP+/QSFP" },
  { slug: "console", label: "Console / Serial", description: "RS-232 / UART management console port" },
  { slug: "bmc", label: "BMC / IPMI", description: "Out-of-band baseboard management controller" },
  { slug: "mgmt", label: "Management", description: "Out-of-band management network" },
  { slug: "dmz", label: "DMZ", description: "Demilitarized zone / perimeter" },
  { slug: "vlan", label: "VLAN", description: "Logical virtual LAN segment" },
  { slug: "vpn", label: "VPN", description: "Encrypted tunnel / remote access" },
  { slug: "custom", label: "Custom", description: "Manually typed or unclassified" },
];
