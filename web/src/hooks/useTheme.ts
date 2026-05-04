import { useState, useEffect, useCallback } from 'react';

type Theme = 'light' | 'dark' | 'system';

function applyThemeToDom(newTheme: Theme) {
  const root = window.document.documentElement;
  const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

  root.classList.remove('light', 'dark');

  const effectiveTheme = newTheme === 'system'
    ? (systemPrefersDark ? 'dark' : 'light')
    : newTheme;

  root.classList.add(effectiveTheme);
  root.setAttribute('data-theme', effectiveTheme);
  localStorage.setItem('theme', newTheme);
  return effectiveTheme;
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window !== 'undefined') {
      return (localStorage.getItem('theme') as Theme) || 'system';
    }
    return 'system';
  });

  const [effectiveTheme, setEffectiveTheme] = useState<'light' | 'dark'>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('theme') as Theme | null;
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const t = stored || 'system';
      return t === 'system' ? (systemPrefersDark ? 'dark' : 'light') : (t as 'light' | 'dark');
    }
    return 'light';
  });

  // Apply theme whenever theme state changes
  useEffect(() => {
    const effective = applyThemeToDom(theme);
    setEffectiveTheme(effective);
  }, [theme]);

  // Listen for system theme changes when in 'system' mode
  useEffect(() => {
    if (theme !== 'system') return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      const effective = applyThemeToDom('system');
      setEffectiveTheme(effective);
    };
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const newTheme = prev === 'light' ? 'dark' : prev === 'dark' ? 'system' : 'light';
      applyThemeToDom(newTheme);
      return newTheme;
    });
  }, []);

  return { theme, setTheme, toggleTheme, effectiveTheme };
}
