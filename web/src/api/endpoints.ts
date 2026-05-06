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
}

export interface DiscoveryResult {
  scanned: number;
  found: number;
  added: number;
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
  enabled: boolean;
  created: string;
}

// Devices API
export const devicesApi = {
  list: () => apiClient.get<Device[]>('/devices'),
  get: (id: string) => apiClient.get<Device>(`/devices/${id}`),
  create: (data: { name: string; ip_address: string; community: string }) =>
    apiClient.post<Device>('/devices', data),
  update: (id: string, data: Partial<Device>) =>
    apiClient.put<Device>(`/devices/${id}`, data),
  delete: (id: string) => apiClient.delete(`/devices/${id}`),
  discover: (data: { network_range: string; community?: string; method?: string }) =>
    apiClient.post<DiscoveryResult>('/discover', data),
};

// Topology API
export const topologyApi = {
  get: () => apiClient.get<TopologyData>('/topology'),
  refresh: () => apiClient.post('/topology/refresh'),
  getStreamUrl: () => `${import.meta.env.DEV ? '/api' : (import.meta.env.VITE_API_URL || 'http://localhost:8000')}/topology/stream`,
};

// Service Checks API
export const checksApi = {
  list: () => apiClient.get<ServiceCheck[]>('/checks'),
  get: (id: string) => apiClient.get<ServiceCheck>(`/checks/${id}`),
  create: (data: {
    name: string;
    check_type: string;
    target: string;
    interval_seconds?: number;
    timeout_seconds?: number;
    config: Record<string, any>;
    enabled?: boolean;
  }) => apiClient.post<ServiceCheck>('/checks', data),
  update: (id: string, data: Partial<ServiceCheck>) =>
    apiClient.put<ServiceCheck>(`/checks/${id}`, data),
  delete: (id: string) => apiClient.delete(`/checks/${id}`),
  run: (id: string) => apiClient.post<CheckResult>(`/checks/${id}/run`),
  results: (id: string, limit?: number) =>
    apiClient.get<CheckResult[]>(`/checks/${id}/results`, { params: { limit } }),
  stats: () => apiClient.get('/checks/stats'),
};

// Alerts API
export const alertsApi = {
  list: () => apiClient.get<AlertConfig[]>('/alerts'),
  create: (data: {
    name: string;
    alert_type: string;
    channel: string;
    config: Record<string, any>;
    enabled?: boolean;
  }) => apiClient.post<AlertConfig>('/alerts', data),
  delete: (id: string) => apiClient.delete(`/alerts/${id}`),
  test: (id: string) => apiClient.post(`/alerts/${id}/test`),
  history: (limit?: number) =>
    apiClient.get('/alerts/history', { params: { limit } }),
};

// Health API
export const healthApi = {
  check: () => apiClient.get('/health'),
  stats: () => apiClient.get('/stats'),
};
