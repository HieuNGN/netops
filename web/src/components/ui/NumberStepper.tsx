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
        <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mr-3">
          {label}
        </label>
      )}
      <div className="flex items-stretch border border-[#c6c6c6] dark:border-[#525252] rounded-sm overflow-hidden">
        <input
          type="number"
          value={value}
          onChange={handleInputChange}
          min={min}
          max={max}
          className="w-14 px-2 py-2 bg-white dark:bg-[#262626] text-[#161616] dark:text-white text-center outline-none border-r border-[#c6c6c6] dark:border-[#525252] focus:ring-0 focus:border-none"
          style={{ appearance: 'textfield' }}
        />
        <div className="flex flex-col">
          <button
            type="button"
            onClick={handleIncrement}
            className="flex-1 flex items-center justify-center px-2 bg-[#f4f4f4] dark:bg-[#161616] hover:bg-[#e0e0e0] dark:hover:bg-[#262626] border-b border-[#c6c6c6] dark:border-[#525252] transition-colors"
            aria-label="Increment"
          >
            <ChevronUp className="h-3 w-3 text-[#525252] dark:text-[#a8a8a8]" />
          </button>
          <button
            type="button"
            onClick={handleDecrement}
            className="flex-1 flex items-center justify-center px-2 bg-[#f4f4f4] dark:bg-[#161616] hover:bg-[#e0e0e0] dark:hover:bg-[#262626] transition-colors"
            aria-label="Decrement"
          >
            <ChevronDown className="h-3 w-3 text-[#525252] dark:text-[#a8a8a8]" />
          </button>
        </div>
      </div>
    </div>
  );
}
