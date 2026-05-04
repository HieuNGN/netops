import { useState, useEffect, useCallback, useRef } from 'react';

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

  // Dispatch custom event for cross-component sync
  window.dispatchEvent(new CustomEvent('theme-change', { detail: { theme, effective } }));
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem('theme') as Theme | null;
    return stored || 'system';
  });

  const themeRef = useRef<Theme>(theme);
  themeRef.current = theme;

  // Compute isDark once using ref to avoid stale closures
  const isDark = getEffectiveTheme(themeRef.current) === 'dark';

  // Apply theme whenever theme state changes
  useEffect(() => {
    applyThemeToDom(theme);
  }, [theme]);

  // Listen for system theme changes when in 'system' mode
  useEffect(() => {
    if (theme !== 'system') return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      window.dispatchEvent(new CustomEvent('theme-change', {
        detail: { theme: 'system', effective: getEffectiveTheme('system') }
      }));
    };
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  // Listen for theme changes from other components
  useEffect(() => {
    const handleThemeChange = (e: Event) => {
      const customEvent = e as CustomEvent;
      if (customEvent.detail?.theme) {
        setThemeState(customEvent.detail.theme);
      }
    };
    window.addEventListener('theme-change', handleThemeChange);
    return () => window.removeEventListener('theme-change', handleThemeChange);
  }, []);

  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    // Get current theme from ref (not state, to avoid stale closure)
    const currentTheme = themeRef.current;
    // Toggle between light and dark only (don't cycle to system)
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    // Apply immediately for instant effect
    applyThemeToDom(newTheme);
    // Update state
    setThemeState(newTheme);
  }, []);

  return { theme, setTheme, toggleTheme, isDark };
}
