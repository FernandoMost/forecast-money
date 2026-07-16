"use client";

/**
 * lib/i18n.tsx — Lightweight i18n system.
 *
 * - Two locales: "es" (default) and "en"
 * - Preference persisted in localStorage under "locale"
 * - `useT()` returns a typed translation function t(key, vars?)
 * - Supports simple {variable} interpolation in strings
 * - No external dependencies
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import es from "@/messages/es.json";
import en from "@/messages/en.json";

export type Locale = "es" | "en";

const messages: Record<Locale, typeof es> = { es, en };

// ---------------------------------------------------------------------------
// Interpolation helper — replaces {key} placeholders with values
// ---------------------------------------------------------------------------

function interpolate(str: string, vars?: Record<string, string | number>): string {
  if (!vars) return str;
  return str.replace(/\{(\w+)\}/g, (_, key) =>
    vars[key] !== undefined ? String(vars[key]) : `{${key}}`
  );
}

// ---------------------------------------------------------------------------
// Deep-get a dot-notated key from the messages object
// e.g. "dashboard.title" → messages.es.dashboard.title
// ---------------------------------------------------------------------------

function deepGet(obj: Record<string, unknown>, path: string): string {
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return path;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : path;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue>({
  locale: "es",
  setLocale: () => {},
  t: (key) => key,
});

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("es");

  // Hydrate from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem("locale") as Locale | null;
    if (stored === "es" || stored === "en") {
      setLocaleState(stored);
    }
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem("locale", l);
    // Update <html lang> attribute so screen readers see the change
    document.documentElement.lang = l;
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const raw = deepGet(messages[locale] as Record<string, unknown>, key);
      return interpolate(raw, vars);
    },
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useT() {
  return useContext(I18nContext);
}
