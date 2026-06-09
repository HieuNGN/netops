"""Anomaly detection service using rolling Z-score analysis."""

import asyncio
import math
import time
from collections import deque
from typing import Any, Optional


class AnomalyDetector:
    """Detects anomalies in time-series metrics using rolling statistics.
    
    Maintains per-metric rolling windows and computes z-scores.
    Thread-safe for concurrent access from poller and API.
    """
    
    def __init__(self, window_size: int = 100, z_threshold: float = 3.0):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self._windows: dict[str, deque[float]] = {}
        self._anomalies: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    def _key(self, metric_type: str, target_id: str) -> str:
        return f"{metric_type}:{target_id}"
    
    async def record_value(self, metric_type: str, target_id: str, value: float) -> Optional[dict[str, Any]]:
        """Record a metric value and check for anomaly.
        
        Returns anomaly info if detected, None otherwise.
        """
        async with self._lock:
            key = self._key(metric_type, target_id)
            
            if key not in self._windows:
                self._windows[key] = deque(maxlen=self.window_size)
            
            window = self._windows[key]
            window.append(value)
            
            if len(window) < 20:
                return None
            
            values = list(window)
            avg = sum(values) / len(values)
            variance = sum((x - avg) ** 2 for x in values) / len(values)
            std = math.sqrt(variance) if variance > 0 else 0
            
            if std < 0.001:
                return None
            
            z_score = (value - avg) / std
            
            if abs(z_score) >= self.z_threshold:
                anomaly = {
                    "metric_type": metric_type,
                    "target_id": target_id,
                    "current_value": value,
                    "baseline_avg": round(avg, 2),
                    "baseline_std": round(std, 2),
                    "z_score": round(z_score, 2),
                    "magnitude": round(abs(value - avg) / avg * 100, 1) if avg > 0 else 0,
                    "direction": "spike" if z_score > 0 else "drop",
                    "confidence": min(round(abs(z_score) / self.z_threshold * 100), 100),
                    "detected_at": time.time(),
                    "sample_count": len(window),
                }
                self._anomalies[key] = anomaly
                return anomaly
            
            if key in self._anomalies:
                del self._anomalies[key]
            
            return None
    
    async def get_active_anomalies(self) -> list[dict[str, Any]]:
        """Return all currently active anomalies."""
        async with self._lock:
            return list(self._anomalies.values())
    
    async def get_anomaly(self, metric_type: str, target_id: str) -> Optional[dict[str, Any]]:
        """Get anomaly status for a specific metric."""
        async with self._lock:
            key = self._key(metric_type, target_id)
            return self._anomalies.get(key)
    
    async def get_baseline(self, metric_type: str, target_id: str) -> Optional[dict[str, Any]]:
        """Get current baseline stats for a metric."""
        async with self._lock:
            key = self._key(metric_type, target_id)
            window = self._windows.get(key)
            if not window or len(window) < 5:
                return None
            
            values = list(window)
            avg = sum(values) / len(values)
            variance = sum((x - avg) ** 2 for x in values) / len(values)
            std = math.sqrt(variance) if variance > 0 else 0
            
            return {
                "metric_type": metric_type,
                "target_id": target_id,
                "avg": round(avg, 2),
                "std": round(std, 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "sample_count": len(window),
                "window_size": self.window_size,
            }
    
    async def remove_target(self, metric_type: str, target_id: str) -> None:
        """Remove all data for a target (e.g., when device is deleted)."""
        async with self._lock:
            key = self._key(metric_type, target_id)
            self._windows.pop(key, None)
            self._anomalies.pop(key, None)
    
    async def clear(self):
        """Reset all windows and anomalies."""
        async with self._lock:
            self._windows.clear()
            self._anomalies.clear()
