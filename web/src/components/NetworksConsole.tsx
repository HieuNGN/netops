import { useState, useEffect } from 'react';
import { X, Globe, Plus, Trash2 } from 'lucide-react';
import { useNetworks } from '../hooks/useNetworks';
import { InlineEditableField } from './InlineEditableField';
import { NetworkTypeIcon } from './NetworkTypeIcon';
import { TagChips } from './TagChips';
import { useToast } from './ui';
import { NETWORK_TYPES } from '../hooks/useNetworkTypes';

interface Props {
  open: boolean;
  onClose: () => void;
}

function timeAgo(iso: string | null): string {
  if (!iso) return 'never';
  const diff = Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function NetworksConsole({ open, onClose }: Props) {
  const { networks, isLoading, updateNetwork, deleteNetwork, createNetwork } = useNetworks();
  const toast = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newCidr, setNewCidr] = useState('');

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const handleRename = async (id: string, name: string) => {
    try { await updateNetwork({ id, data: { name } }); }
    catch { toast.error('Failed to rename network'); }
  };

  const handleTypeChange = async (id: string, network_type: string) => {
    try { await updateNetwork({ id, data: { network_type } }); }
    catch { toast.error('Failed to update type'); }
  };

  const handleTagsChange = async (id: string, tags: string[]) => {
    try { await updateNetwork({ id, data: { tags } }); }
    catch { toast.error('Failed to update tags'); }
  };

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const handleDelete = async (id: string, name: string) => {
    setDeleteTarget({ id, name });
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try { await deleteNetwork(deleteTarget.id); toast.success(`"${deleteTarget.name}" deleted`); }
    catch { toast.error('Failed to delete'); }
    setDeleteTarget(null);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      await createNetwork({ name: newName.trim(), cidr: newCidr.trim() || undefined });
      setNewName(''); setNewCidr(''); setShowCreate(false);
      toast.success(`"${newName}" created`);
    } catch { toast.error('Failed to create network'); }
  };

  if (!open) return null;

  const totalDevices = networks.reduce((s, n) => s + (n.device_count || 0), 0);

  return (
    <>
      <div className="fixed inset-0 bg-foreground/20 z-40" onClick={onClose} />
      <div className="fixed top-0 right-0 h-full w-[400px] bg-card border-l border-border z-50 flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <div>
            <h2 className="text-xs font-semibold text-foreground">Networks</h2>
            <p className="text-xs text-muted-foreground">{networks.length} networks &middot; {totalDevices} devices</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowCreate(!showCreate)} className="p-1.5 text-muted-foreground hover:bg-muted dark:hover:bg-muted rounded-sm" title="Add network">
              <Plus className="h-4 w-4" />
            </button>
            <button onClick={onClose} className="p-1.5 text-muted-foreground hover:bg-muted dark:hover:bg-muted rounded-sm">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={handleCreate} className="px-4 py-3 border-b border-border bg-background space-y-2">
            <input type="text" placeholder="Network name" value={newName} onChange={(e) => setNewName(e.target.value)} className="w-full px-2 py-1.5 text-xs border border-input dark:border-input bg-card text-foreground rounded-sm" required />
            <input type="text" placeholder="CIDR (optional)" value={newCidr} onChange={(e) => setNewCidr(e.target.value)} className="w-full px-2 py-1.5 text-xs border border-input dark:border-input bg-card text-foreground rounded-sm" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowCreate(false); setNewName(''); setNewCidr(''); }} className="text-xs px-2 py-1 text-muted-foreground">Cancel</button>
              <button type="submit" className="text-xs px-3 py-1 bg-thinkpad-red text-white rounded-sm hover:bg-thinkpad-red-hover">Create</button>
            </div>
          </form>
        )}

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {isLoading && <p className="text-xs text-muted-foreground py-4 text-center">Loading...</p>}
          {!isLoading && networks.length === 0 && (
            <div className="text-center py-12">
              <Globe className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">No networks yet</p>
              <button onClick={() => setShowCreate(true)} className="mt-2 text-xs text-destructive hover:underline">Create your first network</button>
            </div>
          )}
          {networks.map((n) => (
              <div
                key={n.id}
                className={`border rounded-sm p-3 ${n.is_default ? 'border-primary bg-background' : 'border-border'}`}
              >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2 min-w-0">
                  <NetworkTypeIcon type={n.network_type} />
                  <InlineEditableField
                    value={n.name}
                    onSave={(v) => handleRename(n.id, v)}
                    className="text-xs font-medium text-foreground"
                  />
                  {n.is_default && (
                    <span className="text-xs px-1.5 py-0.5 bg-ibm-blue text-white dark:bg-ibm-blue dark:text-white rounded-sm font-medium">default</span>
                  )}
                </div>
                <button
                  onClick={() => handleDelete(n.id, n.name)}
                  className="p-1 text-muted-foreground hover:text-destructive shrink-0 rounded-sm hover:bg-badge-destructive-bg"
                  title="Delete network"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                {n.cidr && <span>{n.cidr}</span>}
                {n.cidr && <span>&middot;</span>}
                <span>{n.device_count || 0} devices</span>
                <span>&middot;</span>
                <span>scan: {timeAgo(n.last_scanned)}</span>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <select
                  value={n.network_type || ''}
                  onChange={(e) => handleTypeChange(n.id, e.target.value)}
                  className="text-xs px-2 py-1 border border-border bg-card text-foreground rounded-sm cursor-pointer"
                >
                  <option value="">type...</option>
                  {NETWORK_TYPES.map((t) => (
                    <option key={t.slug} value={t.slug}>{t.label}</option>
                  ))}
                </select>
                <TagChips tags={n.tags || []} onChange={(tags) => handleTagsChange(n.id, tags)} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {deleteTarget && (
        <div className="fixed inset-0 bg-foreground/20 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-sm p-6 max-w-sm w-full mx-4">
            <h3 className="font-semibold mb-2">Confirm Delete</h3>
            <p className="text-xs text-muted-foreground mb-4">
              Delete <strong>"{deleteTarget.name}"</strong>? This will unassign all associated devices.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteTarget(null)} className="px-3 py-1.5 text-xs rounded border border-input">Cancel</button>
              <button onClick={confirmDelete} className="px-3 py-1.5 text-xs rounded bg-thinkpad-red text-white hover:bg-thinkpad-red-hover">Delete</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
