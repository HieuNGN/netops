import { useState } from 'react';
import { X } from 'lucide-react';

interface Props {
  tags: string[];
  onChange: (tags: string[]) => Promise<void>;
}

export function TagChips({ tags, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const addTag = async () => {
    const t = draft.trim().replace(/,+$/, '');
    if (!t || tags.includes(t) || tags.length >= 5 || t.length > 20) return;
    await onChange([...tags, t]);
    setDraft('');
    setEditing(false);
  };

  const removeTag = async (tag: string) => {
    await onChange(tags.filter((t) => t !== tag));
  };

  return (
    <div className="flex flex-wrap items-center gap-1">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-[#e0e0e0] dark:bg-[#393939] text-[#161616] dark:text-[#e0e0e0] text-xs rounded-sm"
        >
          {tag}
          <button onClick={() => removeTag(tag)} className="hover:text-[#da1e28]"><X className="h-2.5 w-2.5" /></button>
        </span>
      ))}
      {editing ? (
        <input
          autoFocus
          type="text"
          value={draft}
          onChange={(e) => { if (e.target.value.includes(',')) { setDraft(e.target.value); addTag(); } else setDraft(e.target.value); }}
          onBlur={addTag}
          onKeyDown={(e) => { if (e.key === 'Enter') addTag(); if (e.key === 'Escape') { setEditing(false); setDraft(''); } }}
          placeholder="new tag..."
          maxLength={20}
          className="w-20 px-1 py-0.5 text-xs border rounded-sm bg-white dark:bg-[#262626] border-[#c6c6c6] dark:border-[#525252] text-[#161616] dark:text-white outline-none focus:border-[#da1e28]"
        />
      ) : (
        tags.length < 5 && (
          <button
            onClick={() => setEditing(true)}
            className="px-1.5 py-0.5 text-xs border border-dashed border-[#c6c6c6] dark:border-[#525252] text-[#a8a8a8] hover:text-[#525252] rounded-sm"
          >
            + tag
          </button>
        )
      )}
    </div>
  );
}
