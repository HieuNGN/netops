import { useState } from 'react';
import { Link } from 'react-router-dom';
import { X, MessageSquare, ArrowRight } from 'lucide-react';

const BANNER_KEY = 'netops_post_signup_banner';

export function PostSignupBanner() {
  const [visible, setVisible] = useState(
    () => localStorage.getItem(BANNER_KEY) === '1',
  );

  const dismiss = () => {
    localStorage.removeItem(BANNER_KEY);
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="bg-btn-destructive text-btn-destructive-foreground border-b border-[#a3151f] font-mono">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex items-center gap-3">
        <MessageSquare className="h-4 w-4 shrink-0" />
        <p className="text-xs flex-1 leading-snug">
          <span className="uppercase tracking-[0.2em] font-bold mr-2">welcome, operator.</span>
          Add a Telegram (or Slack) integration, then create an alert rule that uses it. One bot, many rules, no duplicates.
        </p>
        <Link
          to="/settings?focus=integrations"
          onClick={dismiss}
          className="flex items-center gap-1 px-3 py-1 bg-white text-[#da1e28] text-[10px] uppercase tracking-[0.2em] font-bold hover:bg-black hover:text-white border border-white"
        >
          Configure <ArrowRight className="h-3 w-3" />
        </Link>
        <button
          onClick={dismiss}
          aria-label="Dismiss"
          className="text-white/80 hover:text-white p-1"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
