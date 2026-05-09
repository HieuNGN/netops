import { useState } from 'react';
import { Plus, Trash2, Check, Globe } from 'lucide-react';
import { useNetworks } from '../hooks/useNetworks';
import { useToast } from './ui';

export function NetworkPicker() {
  const { networks, isLoading, createNetwork, deleteNetwork, setDefaultNetwork } = useNetworks();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);
  const [newNetwork, setNewNetwork] = useState({ name: '', cidr: '', description: '' });

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

  const handleDelete = async (id: string, name: string) => {
    if (confirm(`Delete network "${name}"? Devices in this network will be unassigned.`)) {
      try {
        await deleteNetwork(id);
        toast.success('Network deleted');
      } catch {
        toast.error('Failed to delete network');
      }
    }
  };

  if (isLoading) {
    return <div className="text-sm text-[#525252]">Loading networks...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[#161616] dark:text-white flex items-center gap-2">
          <Globe className="h-4 w-4 text-[#da1e28]" />
          Networks
        </h3>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1 text-xs px-2 py-1 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
        >
          <Plus className="h-3 w-3" />
          New Network
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-[#f4f4f4] dark:bg-[#161616] border border-[#e0e0e0] dark:border-[#393939] p-3 rounded-sm space-y-2">
          <input
            type="text"
            placeholder="Network name (e.g. Home Lab)"
            value={newNetwork.name}
            onChange={(e) => setNewNetwork({ ...newNetwork, name: e.target.value })}
            className="w-full px-2 py-1.5 text-sm border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm"
            required
          />
          <input
            type="text"
            placeholder="CIDR (e.g. 192.168.1.0/24)"
            value={newNetwork.cidr}
            onChange={(e) => setNewNetwork({ ...newNetwork, cidr: e.target.value })}
            className="w-full px-2 py-1.5 text-sm border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm"
          />
          <input
            type="text"
            placeholder="Description (optional)"
            value={newNetwork.description}
            onChange={(e) => setNewNetwork({ ...newNetwork, description: e.target.value })}
            className="w-full px-2 py-1.5 text-sm border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm"
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowForm(false)} className="text-xs px-2 py-1 text-[#525252]">Cancel</button>
            <button type="submit" className="text-xs px-3 py-1 bg-[#da1e28] text-white rounded-sm hover:bg-[#a3151f]">Create</button>
          </div>
        </form>
      )}

      <div className="space-y-1">
        {networks.length === 0 && (
          <p className="text-xs text-[#a8a8a8] italic">No networks yet. Create one to start discovering devices.</p>
        )}
        {networks.map((n) => (
          <div
            key={n.id}
            className={`flex items-center justify-between px-3 py-2 rounded-sm border text-sm cursor-pointer transition-colors ${
              n.is_default
                ? 'bg-[#161616] text-white dark:bg-[#f4f4f4] dark:text-[#161616] border-[#161616] dark:border-[#f4f4f4]'
                : 'bg-white dark:bg-[#262626] border-[#e0e0e0] dark:border-[#393939] hover:bg-[#f4f4f4] dark:hover:bg-[#393939]'
            }`}
            onClick={() => handleSetDefault(n.id)}
          >
            <div className="flex items-center gap-2 truncate">
              {n.is_default && <Check className="h-3 w-3 text-[#24a148] dark:text-[#24a148]" />}
              <span className="font-medium truncate">{n.name}</span>
              {n.cidr && <span className="text-xs text-[#525252] dark:text-[#a8a8a8]">{n.cidr}</span>}
            </div>
            {!n.is_default && (
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(n.id, n.name); }}
                className="text-[#da1e28] hover:text-red-900 opacity-60 hover:opacity-100"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
