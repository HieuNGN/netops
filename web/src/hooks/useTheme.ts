import { useState, useEffect, useCallback } from 'react';

type Theme = 'light' | 'dark' | 'system';

function getEffectiveTheme(theme: Theme): 'light' | 'dark' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return theme;
}

function applyThemeToDom(theme: Theme) {
  const root = window.document.documentElement;
  const effective = getEffectiveTheme(theme);

  root.classList.remove('light', 'dark');
  root.classList.add(effective);
  root.setAttribute('data-theme', effective);
  localStorage.setItem('theme', theme);
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>('system');

  // Initialize from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem('theme') as Theme | null;
    if (stored) {
      setTheme(stored);
      applyThemeToDom(stored);
    }
  }, []);

  // Apply theme whenever theme state changes
  useEffect(() => {
    applyThemeToDom(theme);
  }, [theme]);

  // Listen for system theme changes when in 'system' mode
  useEffect(() => {
    if (theme !== 'system') return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => applyThemeToDom('system');
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

  return { theme, setTheme, toggleTheme };
}
