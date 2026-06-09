import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Clock, Activity, AlertCircle } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useDevice } from '../hooks/useDevice';
import { useAnomalies } from '../hooks/useAnomalies';
import { devicesApi, anomaliesApi } from '../api/endpoints';
import { AnomalyBadge } from '../components/AnomalyBadge';
import type { PollHistoryEntry } from '../api/endpoints';

export function DeviceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: device, isLoading, error } = useDevice(id);
  
  const { data: historyData } = useQuery({
    queryKey: ['device-history', id],
    queryFn: async () => {
      if (!id) throw new Error('Device ID required');
      const res = await devicesApi.history(id, 100);
      return res.data;
    },
    enabled: !!id,
  });

  const { anomalies } = useAnomalies();
  
  const { data: baseline } = useQuery({
    queryKey: ['baseline', 'response_time', id],
    queryFn: async () => {
      if (!id) throw new Error('Device ID required');
      const res = await anomaliesApi.baseline('response_time', id);
      return res.data;
    },
    enabled: !!id,
    retry: false,  // Don't retry on 404 (not enough data)
  });

  const currentAnomaly = anomalies.find(
    (a) => a.metric_type === 'response_time' && a.target_id === id
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-destructive mx-auto"></div>
          <p className="text-muted-foreground mt-4">Loading device...</p>
        </div>
      </div>
    );
  }

  if (error || !device) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
          <p className="text-foreground">Device not found</p>
          <button
            onClick={() => navigate('/devices')}
            className="mt-4 px-4 py-2 bg-destructive text-white rounded hover:bg-destructive/90"
          >
            Back to Devices
          </button>
        </div>
      </div>
    );
  }

  const history = historyData?.history || [];
  const chartData = history
    .slice()
    .reverse()
    .map((entry: PollHistoryEntry) => ({
      time: new Date(entry.polled_at).toLocaleTimeString(),
      responseTime: entry.response_time_ms,
      status: entry.status,
    }));

  const statusColors: Record<string, string> = {
    online: 'bg-success',
    offline: 'bg-destructive',
    unknown: 'bg-muted-foreground',
    discovered: 'bg-info',
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      <button
        onClick={() => navigate('/devices')}
        className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Devices
      </button>

      <div className="bg-card rounded-lg border border-border p-6 mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground mb-2">
              {device.name || device.ip_address}
            </h1>
            <p className="text-sm text-muted-foreground">{device.ip_address}</p>
          </div>
          <div className={`px-3 py-1 rounded-full text-xs font-medium text-white ${statusColors[device.status] || 'bg-muted-foreground'}`}>
            {device.status}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground mb-1">SNMP Version</p>
            <p className="text-foreground font-medium">{device.snmp_version}</p>
          </div>
          <div>
            <p className="text-muted-foreground mb-1">Discovery Method</p>
            <p className="text-foreground font-medium">{device.discovery_method || 'manual'}</p>
          </div>
          <div>
            <p className="text-muted-foreground mb-1">Last Polled</p>
            <p className="text-foreground font-medium">
              {device.last_polled ? new Date(device.last_polled).toLocaleString() : 'Never'}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground mb-1">Created</p>
            <p className="text-foreground font-medium">
              {new Date(device.created).toLocaleDateString()}
            </p>
          </div>
        </div>

        {device.sys_descr && (
          <div className="mt-4 pt-4 border-t border-border">
            <p className="text-muted-foreground mb-1">System Description</p>
            <p className="text-foreground text-sm">{device.sys_descr}</p>
          </div>
        )}
      </div>

      <div className="bg-card rounded-lg border border-border p-6">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="h-5 w-5 text-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Poll History</h2>
          <span className="text-sm text-muted-foreground">({history.length} entries)</span>
        </div>

        {currentAnomaly && (
          <div className="mb-4">
            <AnomalyBadge anomaly={currentAnomaly} />
          </div>
        )}

        {chartData.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            <div className="text-center">
              <Clock className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>No poll history available</p>
            </div>
          </div>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis 
                  dataKey="time" 
                  stroke="var(--muted-foreground)"
                  style={{ fontSize: '12px' }}
                />
                <YAxis 
                  stroke="var(--muted-foreground)"
                  style={{ fontSize: '12px' }}
                  label={{ value: 'Response Time (ms)', angle: -90, position: 'insideLeft', fill: 'var(--muted-foreground)' }}
                />
                <Tooltip 
                  contentStyle={{
                    backgroundColor: 'var(--card)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                  }}
                />
                {baseline && (
                  <ReferenceLine 
                    y={baseline.avg} 
                    stroke="var(--ibm-blue)" 
                    strokeDasharray="3 3"
                    label={{ value: `Baseline: ${baseline.avg}ms`, position: 'right', fill: 'var(--ibm-blue)', fontSize: 12 }}
                  />
                )}
                <Line 
                  type="monotone" 
                  dataKey="responseTime" 
                  stroke="var(--destructive)"
                  strokeWidth={2}
                  dot={{ fill: 'var(--destructive)', r: 3 }}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {history.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-medium text-foreground mb-3">Recent Polls</h3>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {history.slice(0, 20).map((entry: PollHistoryEntry) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between p-3 bg-muted/50 rounded border border-border"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${statusColors[entry.status] || 'bg-muted-foreground'}`} />
                    <div>
                      <p className="text-sm text-foreground">
                        {new Date(entry.polled_at).toLocaleString()}
                      </p>
                      {entry.error && (
                        <p className="text-xs text-destructive mt-1">{entry.error}</p>
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    {entry.response_time_ms !== null ? (
                      <p className="text-sm font-medium text-foreground">
                        {entry.response_time_ms}ms
                      </p>
                    ) : (
                      <p className="text-sm text-muted-foreground">N/A</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default DeviceDetail;
