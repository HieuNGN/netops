import { useState } from 'react';
import { Plus, Trash2, Check, Globe, AlertTriangle } from 'lucide-react';
import { useNetworks } from '../hooks/useNetworks';
import { useToast } from './ui';

export function NetworkPicker() {
  const { networks, isLoading, createNetwork, deleteNetwork, setDefaultNetwork } = useNetworks();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);
  const [newNetwork, setNewNetwork] = useState({ name: '', cidr: '', description: '' });
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [deleteTargetName, setDeleteTargetName] = useState('');

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNetwork.name.trim()) return;
    try {
      await createNetwork(newNetwork);
      toast.success(`Network "${newNetwork.name}" created`);
      setNewNetwork({ name: '', cidr: '', description: '' });
      setShowForm(false);
    } catch {
      toast.error('Failed to create network');
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      await setDefaultNetwork(id);
      toast.success('Default network updated');
    } catch {
      toast.error('Failed to set default');
    }
  };

  const handleDelete = (id: string, name: string) => {
    setDeleteTargetId(id);
    setDeleteTargetName(name);
  };

  const confirmDelete = async () => {
    if (!deleteTargetId) return;
    try {
      await deleteNetwork(deleteTargetId);
      toast.success('Network deleted');
    } catch {
      toast.error('Failed to delete network');
    }
    setDeleteTargetId(null);
    setDeleteTargetName('');
  };

  if (isLoading) {
    return <div className="text-xs text-muted-foreground">Loading networks...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-foreground flex items-center gap-2">
          <Globe className="h-4 w-4 text-destructive" />
          Networks
        </h3>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1 text-xs px-2 py-1 bg-ibm-blue text-white rounded-sm hover:bg-ibm-blue-hover"
        >
          <Plus className="h-3 w-3" />
          New Network
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-background border border-border p-3 rounded-sm space-y-2">
          <input
            type="text"
            placeholder="Network name (e.g. Home Lab)"
            value={newNetwork.name}
            onChange={(e) => setNewNetwork({ ...newNetwork, name: e.target.value })}
            className="w-full px-2 py-1.5 text-xs border border-input dark:border-input bg-card text-foreground rounded-sm"
            required
          />
          <input
            type="text"
            placeholder="CIDR (e.g. 192.168.1.0/24)"
            value={newNetwork.cidr}
            onChange={(e) => setNewNetwork({ ...newNetwork, cidr: e.target.value })}
            className="w-full px-2 py-1.5 text-xs border border-input dark:border-input bg-card text-foreground rounded-sm"
          />
          <input
            type="text"
            placeholder="Description (optional)"
            value={newNetwork.description}
            onChange={(e) => setNewNetwork({ ...newNetwork, description: e.target.value })}
            className="w-full px-2 py-1.5 text-xs border border-input dark:border-input bg-card text-foreground rounded-sm"
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowForm(false)} className="text-xs px-2 py-1 text-muted-foreground">Cancel</button>
            <button type="submit" className="text-xs px-3 py-1 bg-thinkpad-red text-white rounded-sm hover:bg-thinkpad-red-hover">Create</button>
          </div>
        </form>
      )}

      <div className="space-y-1">
        {networks.length === 0 && (
          <p className="text-xs text-muted-foreground italic">No networks yet. Create one to start discovering devices.</p>
        )}
        {networks.map((n) => (
          <div
            key={n.id}
            className={`flex items-center justify-between px-3 py-2 rounded-sm border text-xs cursor-pointer transition-colors ${
                n.is_default
                  ? 'bg-ibm-blue text-white dark:bg-ibm-blue dark:text-white border-ibm-blue'
                  : 'bg-card border-border hover:bg-muted dark:hover:bg-muted'
            }`}
            onClick={() => handleSetDefault(n.id)}
          >
            <div className="flex items-center gap-2 truncate">
              {n.is_default && <Check className="h-3 w-3 text-success" />}
              <span className="font-medium truncate">{n.name}</span>
              {n.cidr && <span className="text-xs text-muted-foreground">{n.cidr}</span>}
            </div>
            {!n.is_default && (
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(n.id, n.name); }}
                className="text-destructive hover:text-destructive opacity-60 hover:opacity-100"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Delete confirmation modal */}
      {deleteTargetId && (
        <div className="fixed inset-0 bg-foreground/20 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-sm p-6 max-w-sm w-full mx-4">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="h-5 w-5 text-thinkpad-red" />
              <h3 className="font-semibold text-foreground">Delete Network</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-4">
              Are you sure you want to delete <span className="font-medium text-foreground">{deleteTargetName}</span>? Devices in this network will be unassigned.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => { setDeleteTargetId(null); setDeleteTargetName(''); }}
                className="px-4 py-2 text-xs rounded-sm border border-input text-foreground hover:bg-surface-hover"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="px-4 py-2 text-xs rounded-sm bg-thinkpad-red text-white hover:bg-thinkpad-red-hover"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
