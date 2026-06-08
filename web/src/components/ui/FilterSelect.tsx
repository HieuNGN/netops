export function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  const active = value !== 'all';
  return (
    <div
      className={`inline-flex items-center text-xs rounded-sm border overflow-hidden transition-colors ${
        active
          ? 'border-ibm-blue bg-ibm-blue/5 text-foreground'
          : 'border-input bg-card text-foreground'
      }`}
    >
      <span className={`px-2 py-1 font-medium ${active ? 'text-ibm-blue' : 'text-muted-foreground'}`}>
        {label}:
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent px-1.5 py-1 text-xs text-foreground focus:outline-none cursor-pointer"
      >
        <option value="all">all</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
