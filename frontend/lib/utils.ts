// lib/utils.ts — shared formatting utilities

export function formatEur(amount: number): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(amount);
}

export function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export const STATUS_COLORS: Record<string, string> = {
  green: "text-green-600 bg-green-50 border-green-200",
  amber: "text-yellow-700 bg-yellow-50 border-yellow-200",
  red: "text-red-600 bg-red-50 border-red-200",
};

export const STATUS_BADGE: Record<string, string> = {
  green: "bg-green-100 text-green-800",
  amber: "bg-yellow-100 text-yellow-800",
  red: "bg-red-100 text-red-800",
};

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
