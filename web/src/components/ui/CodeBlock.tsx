import { useState, useRef, useEffect } from 'react';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  /** The text the user can copy. */
  value: string;
  /** Optional className for the outer wrapper. */
  className?: string;
  /** Render the value in an inline <code> (single line) or a <pre> (multiline). Default: detect by \n. */
  inline?: boolean;
}

export function CodeBlock({ value, className = '', inline }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  const handleCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const ta = document.createElement('textarea');
        ta.value = value;
        ta.setAttribute('readonly', '');
        ta.style.position = 'absolute';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Silent — the user can still select and Ctrl+C.
    }
  };

  const isBlock = inline === true ? false : inline === false ? true : value.includes('\n');
  const baseCls =
    'block bg-surface-subtle border border-border rounded-sm font-mono text-[12px] text-foreground/90 px-2 py-1.5 break-all whitespace-pre-wrap';

  return (
    <div className={`relative group ${className}`}>
      {isBlock ? (
        <pre className={baseCls}>{value}</pre>
      ) : (
        <code className={baseCls}>{value}</code>
      )}
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? 'Copied' : 'Copy to clipboard'}
        title={copied ? 'Copied' : 'Copy'}
        className={`absolute top-1 right-1 inline-flex items-center justify-center w-6 h-6 rounded-sm text-muted-foreground hover:text-foreground hover:bg-surface-hover transition-colors ${
          copied ? 'copy-pulse text-ibm-green' : ''
        }`}
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
