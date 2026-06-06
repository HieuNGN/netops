import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { HelpCircle, X } from 'lucide-react';

type Placement = 'right' | 'left' | 'bottom';

interface HintPopoverProps {
  /** Popover heading. */
  title: string;
  /** Popover body content. */
  children: ReactNode;
  /** Trigger aria-label. Defaults to "What is this?". */
  triggerLabel?: string;
  /** Width in px. Default 320. */
  width?: number;
  /** Force placement, or 'auto' to flip based on viewport. Default 'auto'. */
  placement?: 'auto' | Placement;
  /** Extra class for the panel. */
  className?: string;
}

/**
 * Inline help popover. Triggered by a small `?` button. Anchors beside the
 * field, auto-flips when there's no room. Closes on outside click, Escape,
 * or trigger toggle.
 */
export function HintPopover({
  title,
  children,
  triggerLabel = 'What is this?',
  width = 320,
  placement = 'auto',
  className = '',
}: HintPopoverProps) {
  const [open, setOpen] = useState(false);
  const [resolved, setResolved] = useState<Placement>('right');
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Close on outside click / Escape
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (
        panelRef.current?.contains(t) ||
        triggerRef.current?.contains(t)
      ) {
        return;
      }
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Decide placement once the panel has measured itself
  useLayoutEffect(() => {
    if (!open) return;
    if (placement !== 'auto') {
      setResolved(placement);
      return;
    }
    const trigger = triggerRef.current;
    if (!trigger) return;
    const r = trigger.getBoundingClientRect();
    const vw = window.innerWidth;
    const margin = 12;
    const fitsRight = r.right + width + margin < vw;
    const fitsLeft = r.left - width - margin > 0;
    if (fitsRight) setResolved('right');
    else if (fitsLeft) setResolved('left');
    else setResolved('bottom');
  }, [open, placement, width]);

  // Reposition on scroll/resize while open
  useEffect(() => {
    if (!open) return;
    const reflow = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const r = trigger.getBoundingClientRect();
      const vw = window.innerWidth;
      const margin = 12;
      const fitsRight = r.right + width + margin < vw;
      const fitsLeft = r.left - width - margin > 0;
      if (fitsRight) setResolved('right');
      else if (fitsLeft) setResolved('left');
      else setResolved('bottom');
    };
    window.addEventListener('scroll', reflow, true);
    window.addEventListener('resize', reflow);
    return () => {
      window.removeEventListener('scroll', reflow, true);
      window.removeEventListener('resize', reflow);
    };
  }, [open, width]);

  const toggle = () => setOpen((o) => !o);

  // Anchor offset: align panel top with trigger mid; clamp so panel never
  // spills above viewport.
  const offsetStyle: React.CSSProperties = (() => {
    if (resolved === 'right') return { left: 'calc(100% + 8px)', top: '-6px' };
    if (resolved === 'left') return { right: 'calc(100% + 8px)', top: '-6px' };
    return { top: 'calc(100% + 8px)', left: 0 };
  })();

  return (
    <span className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        aria-label={triggerLabel}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={`${title} — click for help`}
        className={`inline-flex items-center justify-center w-4 h-4 rounded-full border transition-colors ${
          open
            ? 'border-thinkpad-red text-thinkpad-red bg-thinkpad-red/10'
            : 'border-border text-muted-foreground hover:text-foreground hover:border-foreground/40'
        }`}
      >
        <HelpCircle className="h-3 w-3" />
      </button>

      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label={title}
          style={{ ...offsetStyle, width }}
          className={`absolute z-50 hint-popover-in bg-card border border-border rounded-sm shadow-lg shadow-black/30 ${className}`}
        >
          <div className="flex items-start justify-between gap-2 px-3 py-2 border-b border-border bg-surface-subtle">
            <h4 className="text-xs font-mono font-semibold uppercase tracking-wider text-foreground">
              {title}
            </h4>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close help"
              className="text-muted-foreground hover:text-foreground -mr-1 -mt-0.5 p-0.5"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="p-3 max-h-80 overflow-y-auto">{children}</div>
        </div>
      )}
    </span>
  );
}
