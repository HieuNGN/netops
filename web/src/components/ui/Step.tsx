import type { ReactNode } from 'react';

interface StepProps {
  n: number;
  children: ReactNode;
}

/** Numbered step row used inside hint popovers. */
export function Step({ n, children }: StepProps) {
  return (
    <li className="flex gap-2 items-start">
      <span
        aria-hidden
        className="shrink-0 inline-flex items-center justify-center w-5 h-5 mt-px rounded-sm bg-thinkpad-red text-white text-[11px] font-mono font-bold leading-none"
      >
        {n}
      </span>
      <span className="text-[13px] leading-snug text-foreground/90">{children}</span>
    </li>
  );
}
