import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, Server, AlertTriangle, Check, Settings as SettingsIcon } from 'lucide-react';
import { useSetProfile } from '../hooks/useConfig';
import { useToast } from './ui/Toast';

export type EnvironmentProfileName = 'homelab' | 'small_business' | 'datacenter';

const PROFILE_META: Record<EnvironmentProfileName, string> = {
  homelab: 'Up to 15 devices. Polling every 30s, rescans every 6h.',
  small_business: 'Up to 80 devices. Polling every 60s, rescans every 2h.',
  datacenter: 'Unlimited devices. Polling every 60s, rescans every 1h.',
};

interface ProfileConfirmModalProps {
  open: boolean;
  detectedProfile: EnvironmentProfileName;
  deviceCount: number;
  source: 'startup' | 'runtime' | 'manual';
  onDismiss: () => void;
  onConfirmed: () => void;
}

export function ProfileConfirmModal({
  open,
  detectedProfile,
  deviceCount,
  source,
  onDismiss,
  onConfirmed,
}: ProfileConfirmModalProps) {
  const setProfile = useSetProfile();
  const toast = useToast();
  const navigate = useNavigate();
  const [pending, setPending] = useState<EnvironmentProfileName | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const confirm = async (name: EnvironmentProfileName) => {
    setBusy(true);
    try {
      await setProfile.mutateAsync({ profile: name, confirmed: true });
      toast.success(`Profile set to ${name}`, 'Auto-detected profile confirmed');
      onConfirmed();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err as { message?: string })?.message ||
        'Profile confirm failed';
      toast.error(detail);
    } finally {
      setBusy(false);
    }
  };

  const pickAnother = () => {
    onDismiss();
    navigate('/settings');
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="profile-confirm-title"
    >
      <div className="bg-card border border-border rounded-sm shadow-2xl max-w-lg w-full mx-4">
        <div className="px-5 py-3 border-b border-border bg-surface-subtle flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-muted-foreground" />
            <h2 id="profile-confirm-title" className="text-xs font-semibold text-foreground">
              Detected new network
            </h2>
          </div>
          <button
            onClick={onDismiss}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div className="flex items-start gap-2 px-3 py-2 rounded-sm bg-ibm-yellow/10 border border-ibm-yellow/30 text-xs text-foreground">
            <AlertTriangle className="h-3.5 w-3.5 text-ibm-yellow shrink-0 mt-0.5" />
            <span>
              <span className="font-medium">Auto-detected</span> based on{' '}
              {deviceCount} device{deviceCount === 1 ? '' : 's'} on this network
              {source === 'startup' ? ' (startup scan)' : source === 'runtime' ? ' (runtime scan)' : ''}.
              Confirm to lock the poll/scan cadence, or pick another tier.
            </span>
          </div>
          <div className="grid grid-cols-1 gap-2">
            {(['homelab', 'small_business', 'datacenter'] as EnvironmentProfileName[]).map((p) => (
              <button
                key={p}
                onClick={() => setPending(p)}
                disabled={busy}
                className={`text-left p-3 rounded-sm border text-xs transition-all disabled:opacity-50 ${
                  pending === p
                    ? 'border-ibm-blue bg-ibm-blue/5 ring-1 ring-ibm-blue/30'
                    : p === detectedProfile
                    ? 'border-ibm-blue/60 bg-ibm-blue/5'
                    : 'border-input hover:bg-surface-hover'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold">{p}</span>
                  {p === detectedProfile && (
                    <span className="text-[10px] uppercase tracking-wide text-ibm-blue font-medium">
                      detected
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground mt-1">{PROFILE_META[p]}</div>
              </button>
            ))}
          </div>
          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
            <button
              onClick={pickAnother}
              disabled={busy}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-sm border border-input text-xs hover:bg-surface-hover disabled:opacity-50"
            >
              <SettingsIcon className="h-3 w-3" />
              Open Settings
            </button>
            <button
              onClick={onDismiss}
              disabled={busy}
              className="px-3 py-1.5 rounded-sm border border-input text-xs hover:bg-surface-hover disabled:opacity-50"
            >
              Dismiss
            </button>
            <button
              onClick={() => pending && confirm(pending)}
              disabled={!pending || busy}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-sm bg-ibm-blue text-white text-xs hover:bg-ibm-blue-hover disabled:opacity-50"
            >
              <Check className="h-3 w-3" />
              {busy ? 'Confirming…' : `Confirm ${pending ?? detectedProfile}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
