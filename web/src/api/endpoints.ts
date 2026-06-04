import apiClient from './client';

// Types
export interface Device {
  id: string;
  name: string;
  ip_address: string;
  community: string;
  status: 'online' | 'offline' | 'unknown' | 'discovered';
  sys_descr: string;
  discovery_method: string;
  last_polled: string;
  created: string;
  updated: string;
  network_id?: string;
  snmp_version: string;
  snmpv3_username: string | null;
  snmpv3_auth_protocol: string | null;
  snmpv3_auth_key: string | null;
  snmpv3_priv_protocol: string | null;
  snmpv3_priv_key: string | null;
}

export interface Network {
  id: string;
  name: string;
  cidr: string;
  description: string;
  is_default: boolean;
  network_type: string | null;
  tags: string[];
  last_scanned: string | null;
  device_count: number;
  created: string;
  updated: string;
}

export interface DiscoveryResult {
  scanned: number;
  found: number;
  added: number;
  cleared?: number;
  by_method: Record<string, number>;
}

export interface TopologyNode {
  id: string;
  device_id: string;
  label: string;
  node_type: string;
  status: 'online' | 'offline' | 'unknown';
  created: string;
  updated: string;
  level?: number;
}

export interface TopologyLink {
  id: string;
  source_id: string;
  target_id: string;
  source_port: string;
  target_port: string;
  status: 'active' | 'inactive';
  created: string;
  updated: string;
}

export interface TopologyData {
  nodes: TopologyNode[];
  links: TopologyLink[];
}

export interface ServiceCheck {
  id: string;
  name: string;
  check_type: 'http' | 'tcp' | 'dns' | 'ping' | 'ssl';
  target: string;
  interval_seconds: number;
  timeout_seconds: number;
  config_json: Record<string, any>;
  enabled: boolean;
  created: string;
  updated: string;
}

export interface CheckResult {
  target_id: string;
  check_type: string;
  status: 'up' | 'down' | 'degraded' | 'unknown';
  response_time_ms: number;
  message: string;
  details: Record<string, any>;
  error: string | null;
  timestamp: string;
}

export interface AlertConfig {
  id: string;
  name: string;
  alert_type: string;
  channel: string;
  config_json: Record<string, any>;
  integration_id: string | null;
  enabled: boolean;
  created: string;
}

export type IntegrationType = 'webhook' | 'slack' | 'telegram' | 'whatsapp' | 'email';

export interface IntegrationConfig {
  id: string;
  type: IntegrationType;
  name: string;
  secrets_json: Record<string, any>;
  enabled: boolean;
  created: string;
}

export interface TopologyHistoryEvent {
  id: number;
  event_type: string;
  node_id: string | null;
  link_id: string | null;
  old_status: string | null;
  new_status: string | null;
  details: Record<string, any>;
  recorded_at: string;
}

// Devices API — all calls prefixed with /api so they don't collide
// with SPA page paths (/devices, /checks, /alerts, /topology).
// Nginx / Vite dev-proxy strips the /api prefix when forwarding
// to FastAPI, which mounts endpoints at the bare path.
export const devicesApi = {
  list: (limit?: number, offset?: number) =>
    apiClient.get<Device[]>('/api/devices', { params: { limit, offset } }),
  get: (id: string) => apiClient.get<Device>(`/api/devices/${id}`),
  create: (data: { name: string; ip_address: string; community: string }) =>
    apiClient.post<Device>('/api/devices', data),
  import: (devices: any[]) => apiClient.post('/api/devices/import', { devices }),
  update: (id: string, data: Partial<Device>) =>
    apiClient.put<Device>(`/api/devices/${id}`, data),
  delete: (id: string) => apiClient.delete(`/api/devices/${id}`),
  clearAll: () => apiClient.delete<{ status: string; removed: number }>('/api/devices'),
  clearMocks: () => apiClient.post<{ status: string; matched: number; removed: number }>('/api/devices/clear-mocks'),
  rescan: (data: { network_range: string; community?: string; method?: string; replace?: boolean }) =>
    apiClient.post<DiscoveryResult>('/api/discover/rescan', data, { timeout: 120000 }),
  discover: (data: { network_range: string; community?: string; method?: string }) =>
    apiClient.post<DiscoveryResult>('/api/discover', data, { timeout: 60000 }),
  getEventsStreamUrl: () => `${import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || '')}/api/events/stream`,
};

// Topology API
export const topologyApi = {
  get: () => apiClient.get<TopologyData>('/api/topology'),
  refresh: () => apiClient.post('/api/topology/refresh'),
  getStreamUrl: () => `${import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || '')}/api/topology/stream`,
  history: (limit?: number, event_type?: string, from_time?: string, to_time?: string, offset?: number) =>
    apiClient.get<{ events: TopologyHistoryEvent[]; total: number }>('/api/topology/history', {
      params: { limit, event_type, from_time, to_time, offset },
    }),
  snapshot: (eventId: number) =>
    apiClient.get<{ event: any; topology: TopologyData; current: TopologyData }>(`/api/topology/snapshot/${eventId}`),
};

// Service Checks API
export const checksApi = {
  list: (limit?: number, offset?: number) =>
    apiClient.get<ServiceCheck[]>('/api/checks', { params: { limit, offset } }),
  get: (id: string) => apiClient.get<ServiceCheck>(`/api/checks/${id}`),
  create: (data: {
    name: string;
    check_type: string;
    target: string;
    interval_seconds?: number;
    timeout_seconds?: number;
    config: Record<string, any>;
    enabled?: boolean;
  }) => apiClient.post<ServiceCheck>('/api/checks', data),
  update: (id: string, data: Partial<ServiceCheck>) =>
    apiClient.put<ServiceCheck>(`/api/checks/${id}`, data),
  delete: (id: string) => apiClient.delete(`/api/checks/${id}`),
  run: (id: string) => apiClient.post<CheckResult>(`/api/checks/${id}/run`),
  results: (id: string, limit?: number) =>
    apiClient.get<CheckResult[]>(`/api/checks/${id}/results`, { params: { limit } }),
  stats: () => apiClient.get('/api/checks/stats'),
};

export interface ActiveAlert {
  key: string;
  alert_type: string;
  target_id: string;
  severity: string;
  title: string;
  message: string;
  status: 'firing' | 'acknowledged';
  fired_at: number;
}

// Alerts API
export const alertsApi = {
  list: (limit?: number, offset?: number) =>
    apiClient.get<AlertConfig[]>('/api/alerts', { params: { limit, offset } }),
  create: (data: {
    name: string;
    alert_type: string;
    channel: string;
    config: Record<string, any>;
    enabled?: boolean;
  }) => apiClient.post<AlertConfig>('/api/alerts', data),
  update: (id: string, data: Partial<AlertConfig>) =>
    apiClient.put<AlertConfig>(`/api/alerts/${id}`, data),
  delete: (id: string) => apiClient.delete(`/api/alerts/${id}`),
  test: (id: string) => apiClient.post(`/api/alerts/${id}/test`),
  history: (limit?: number) =>
    apiClient.get('/api/alerts/history', { params: { limit } }),
  active: () => apiClient.get<{ alerts: ActiveAlert[] }>('/api/alerts/active'),
  acknowledge: (key: string) => apiClient.post(`/api/alerts/active/${key}/acknowledge`),
  resolve: (key: string) => apiClient.post(`/api/alerts/active/${key}/resolve`),
};

export interface MaintenanceWindow {
  id: string;
  name: string;
  start_time: string;
  end_time: string;
  description: string;
  created_at: string;
}

// Maintenance Windows API
export const maintenanceWindowsApi = {
  list: (limit?: number, offset?: number) =>
    apiClient.get<{ windows: MaintenanceWindow[] }>('/api/maintenance-windows', { params: { limit, offset } }),
  create: (data: { name: string; start_time: string; end_time: string; description?: string }) =>
    apiClient.post<{ window: MaintenanceWindow }>('/api/maintenance-windows', data),
  delete: (id: string) => apiClient.delete(`/api/maintenance-windows/${id}`),
};

// Integrations API — global notification credentials (Telegram bot, Slack webhook, etc.)
export const integrationsApi = {
  list: (type?: IntegrationType) =>
    apiClient.get<IntegrationConfig[]>('/api/integrations', { params: { type } }),
  get: (id: string) => apiClient.get<IntegrationConfig>(`/api/integrations/${id}`),
  create: (data: { type: IntegrationType; name: string; secrets_json: Record<string, any>; enabled?: boolean }) =>
    apiClient.post<IntegrationConfig>('/api/integrations', data),
  update: (id: string, data: Partial<{ name: string; secrets_json: Record<string, any>; enabled: boolean }>) =>
    apiClient.put<IntegrationConfig>(`/api/integrations/${id}`, data),
  delete: (id: string) => apiClient.delete<{ status: string; id: string }>(`/api/integrations/${id}`),
  test: (id: string) =>
    apiClient.post<{ sent: boolean; type: string }>(`/api/integrations/${id}/test`),
};

// Networks API
export const networksApi = {
  list: () => apiClient.get<Network[]>('/api/networks'),
  get: (id: string) => apiClient.get<Network>(`/api/networks/${id}`),
  create: (data: { name: string; cidr?: string; description?: string }) =>
    apiClient.post<Network>('/api/networks', data),
  update: (id: string, data: Partial<Network>) =>
    apiClient.put<Network>(`/api/networks/${id}`, data),
  delete: (id: string) => apiClient.delete(`/api/networks/${id}`),
  setDefault: (id: string) => apiClient.post<Network>(`/api/networks/${id}/default`),
  assignDevice: (deviceId: string, networkId: string) =>
    apiClient.post<Device>(`/api/devices/${deviceId}/network/${networkId}`),
};

// Health / Stats API
export const healthApi = {
  check: () => apiClient.get('/api/health'),
  stats: () => apiClient.get('/api/stats'),
  pollHistory: (limit?: number) =>
    apiClient.get('/api/poll-history', { params: { limit } }),
};
