import { useState, useRef, useEffect } from 'react';

interface Props {
  value: string;
  onSave: (newValue: string) => Promise<void>;
  className?: string;
}

export function InlineEditableField({ value, onSave, className }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(value); }, [value]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = async () => {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === value) { setEditing(false); return; }
    setSaving(true);
    try { await onSave(trimmed); setEditing(false); }
    catch { setDraft(value); setEditing(false); }
    finally { setSaving(false); }
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setDraft(value); setEditing(false); } }}
        className={`px-1 py-0.5 text-sm border rounded-sm bg-card border-ring focus:ring-1 focus:ring-ring outline-none text-foreground ${saving ? 'opacity-50' : ''} ${className || ''}`}
        disabled={saving}
      />
    );
  }

  return (
    <span
      onClick={() => setEditing(true)}
      className={`cursor-pointer hover:bg-muted rounded-sm px-1 -mx-1 transition-colors ${className || ''}`}
      title="Click to rename"
    >
      {value}
    </span>
  );
}