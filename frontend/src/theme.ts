import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

// the same key and colors as the script in index.html
const THEME_KEY = "theme";
const BAR_COLORS: Record<Theme, string> = { light: "#f6f7f9", dark: "#14161c" };

const SYSTEM_DARK = "(prefers-color-scheme: dark)";

function savedTheme(): Theme | null {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    return saved === "light" || saved === "dark" ? saved : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia(SYSTEM_DARK).matches ? "dark" : "light";
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", BAR_COLORS[theme]);
}

// follows the system until the user picks a theme
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => savedTheme() ?? systemTheme());

  useEffect(() => {
    apply(theme);
  }, [theme]);

  useEffect(() => {
    const query = window.matchMedia(SYSTEM_DARK);
    const onChange = () => {
      if (savedTheme() === null) {
        setTheme(systemTheme());
      }
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    const next = theme === "dark" ? "light" : "dark";
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // the choice lasts until the page is reloaded
    }
    setTheme(next);
  }, [theme]);

  return [theme, toggle];
}
