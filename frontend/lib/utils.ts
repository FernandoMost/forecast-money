// lib/utils.ts — shared formatting utilities

/**
 * Format a number as EUR currency.
 * locale defaults to "es-ES" but can be overridden (e.g. "en-GB" for English users).
 * The currency is always EUR — this app is Europe-focused.
 */
export function formatEur(amount: number, locale = "es-ES"): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(amount);
}

export function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export const STATUS_COLORS: Record<string, string> = {
  green: "text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/40 border-green-200 dark:border-green-800",
  amber: "text-yellow-700 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-950/40 border-yellow-200 dark:border-yellow-800",
  red:   "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-800",
};

export const STATUS_BADGE: Record<string, string> = {
  green: "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300",
  amber: "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-300",
  red:   "bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300",
};

// Category colors are now stored in the DB and served via GET /api/v1/categories.
// Use `categoryColor(id)` from `@/components/CategoryTree` instead of this object.
// This fallback map is kept for non-component contexts (e.g. chart color seeds)
// and will automatically be overridden once the API responds.
export const CATEGORY_COLORS: Record<string, string> = {
  housing: "#6366f1",
  groceries: "#22c55e",
  restaurants: "#f97316",
  transport: "#0ea5e9",
  subscriptions: "#a855f7",
  shopping: "#ec4899",
  entertainment: "#eab308",
  health: "#14b8a6",
  income: "#84cc16",
  transfers: "#94a3b8",
  cash: "#78716c",
  admin: "#64748b",
  uncategorized: "#d1d5db",
};
