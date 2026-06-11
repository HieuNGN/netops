import { AlertTriangle } from 'lucide-react';
import type { Anomaly } from '../api/endpoints';

export function AnomalyBadge({ anomaly }: { anomaly: Anomaly }) {
  const isSpike = anomaly.direction === 'spike';
  
  return (
    <div className="inline-flex items-center gap-2 px-3 py-2 rounded-sm bg-ibm-yellow/10 border border-ibm-yellow/30">
      <AlertTriangle className="h-4 w-4 text-ibm-yellow" />
      <div className="text-xs">
        <span className="font-medium text-foreground">
          {isSpike ? '↑' : '↓'} {anomaly.magnitude}% {anomaly.direction}
        </span>
        <span className="text-muted-foreground ml-1">
          (baseline: {anomaly.baseline_avg}±{anomaly.baseline_std}ms)
        </span>
      </div>
      <div className="text-xs text-muted-foreground">
        z={anomaly.z_score} · {anomaly.confidence}% confidence
      </div>
    </div>
  );
}

export function AnomalyCount({ count }: { count: number }) {
  if (count === 0) return null;
  
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-sm bg-ibm-yellow/10 border border-ibm-yellow/30">
      <AlertTriangle className="h-4 w-4 text-ibm-yellow" />
      <span className="text-xs font-medium text-foreground">
        {count} anomal{count === 1 ? 'y' : 'ies'} detected
      </span>
    </div>
  );
}
