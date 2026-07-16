"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useT } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import type { Locale } from "@/lib/i18n";

export default function Nav() {
  const pathname = usePathname();
  const { t, locale, setLocale } = useT();
  const { isDark, toggleTheme } = useTheme();

  const links = [
    { href: "/",             label: t("nav.dashboard") },
    { href: "/transactions", label: t("nav.transactions") },
    { href: "/trends",       label: t("nav.trends") },
    { href: "/health",       label: t("nav.health") },
    { href: "/categories",   label: t("nav.categories") },
    { href: "/rules",        label: t("nav.rules") },
    { href: "/upload",       label: t("nav.upload") },
  ];

  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-3 flex items-center gap-4 flex-wrap">
      {/* Brand */}
      <span className="font-bold text-gray-900 dark:text-white text-lg tracking-tight shrink-0">
        Forecast Money
      </span>

      {/* Nav links */}
      <div className="flex gap-1 flex-wrap">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              pathname === link.href
                ? "bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300"
                : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-800"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </div>

      {/* Right side: tagline + controls */}
      <div className="ml-auto flex items-center gap-3">
        <span className="hidden md:block text-xs text-gray-400 dark:text-gray-500">
          {t("nav.tagline")}
        </span>

        {/* Language selector */}
        <div className="flex items-center rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden text-xs font-medium">
          {(["es", "en"] as Locale[]).map((l) => (
            <button
              key={l}
              onClick={() => setLocale(l)}
              className={`px-2.5 py-1.5 transition-colors ${
                locale === l
                  ? "bg-indigo-600 text-white"
                  : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
              aria-label={l === "es" ? "Español" : "English"}
            >
              {l === "es" ? "ES" : "EN"}
            </button>
          ))}
        </div>

        {/* Dark mode toggle */}
        <button
          onClick={toggleTheme}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
          className="p-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          {isDark ? (
            // Sun icon
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 7a5 5 0 100 10A5 5 0 0012 7z" />
            </svg>
          ) : (
            // Moon icon
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          )}
        </button>
      </div>
    </nav>
  );
}
