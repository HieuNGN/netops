import { ChevronUp, ChevronDown } from 'lucide-react';

interface NumberStepperProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  label?: string;
  className?: string;
}

export function NumberStepper({
  value,
  onChange,
  min = 0,
  max = 999,
  label,
  className = '',
}: NumberStepperProps) {
  const handleIncrement = () => {
    if (value < max) onChange(value + 1);
  };

  const handleDecrement = () => {
    if (value > min) onChange(value - 1);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = parseInt(e.target.value, 10);
    if (!isNaN(raw)) {
      onChange(Math.min(Math.max(raw, min), max));
    } else {
      onChange(min);
    }
  };

  return (
    <div className={`flex items-center ${className}`}>
      {label && (
        <label className="block text-sm font-medium text-foreground mr-3">
          {label}
        </label>
      )}
      <div className="flex items-stretch border border-input rounded-sm overflow-hidden">
        <input
          type="number"
          value={value}
          onChange={handleInputChange}
          min={min}
          max={max}
          className="w-14 px-2 py-2 bg-card text-foreground text-center outline-none border-r border-input focus:ring-0 focus:border-none"
          style={{ appearance: 'textfield' }}
        />
        <div className="flex flex-col">
          <button
            type="button"
            onClick={handleIncrement}
            className="flex-1 flex items-center justify-center px-2 bg-background hover:bg-surface-hover border-b border-input transition-colors"
            aria-label="Increment"
          >
            <ChevronUp className="h-3 w-3 text-muted-foreground" />
          </button>
          <button
            type="button"
            onClick={handleDecrement}
            className="flex-1 flex items-center justify-center px-2 bg-background hover:bg-surface-hover transition-colors"
            aria-label="Decrement"
          >
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
    </div>
  );
}