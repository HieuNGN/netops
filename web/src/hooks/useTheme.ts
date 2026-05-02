import { useState, useEffect } from 'react';

type Theme = 'light' | 'dark' | 'system';

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window !== 'undefined') {
      return (localStorage.getItem('theme') as Theme) || 'system';
    }
    return 'system';
  });

  useEffect(() => {
    const root = window.document.documentElement;
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    root.classList.remove('light', 'dark');

    const effectiveTheme = theme === 'system'
      ? (systemPrefersDark ? 'dark' : 'light')
      : theme;

    root.classList.add(effectiveTheme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  return { theme, setTheme };
}
