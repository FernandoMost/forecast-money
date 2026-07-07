// lib/api.ts — typed API client for the FastAPI backend

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${path} → ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST", body });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${path} → ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// --- Types ---

export interface CategoryBreakdown {
  category: string;
  total: number;
  count: number;
}

export interface MonthlySummary {
  month: string;
  tx_count: number;
  total_income: number;
  total_expenses: number;
  net_savings: number;
  savings_rate: number;
  min_balance: number;
  max_balance: number;
  by_category: CategoryBreakdown[];
}

export interface Transaction {
  id: string;
  bank_id: string;
  date: string;
  date_value: string;
  description: string;
  clean_description: string | null;
  clean_description_source: string | null;
  amount: number;
  balance: number;
  currency: string;
  is_reversal: boolean;
  category: string | null;
  subcategory: string | null;
  category_source: string | null;
  month: string;
  year: number;
}

export interface TransactionList {
  total: number;
  limit: number;
  offset: number;
  items: Transaction[];
}

export interface RuleResult {
  rule_id: string;
  name: string;
  status: "green" | "amber" | "red";
  score: number;
  message: string;
  details: Record<string, unknown>;
}

export interface Alert {
  rule_id: string;
  name: string;
  status: "green" | "amber" | "red";
  message: string;
}

export interface HealthScore {
  overall_score: number;
  grade: string;
  months_analyzed: string[];
  summary: {
    total_income: number;
    total_expenses: number;
    net_savings: number;
    months_analyzed: number;
    transaction_count: number;
  };
  rules: RuleResult[];
  alerts: Alert[];
}

export interface UploadResponse {
  import_id: string;
  bank_id: string;
  filename: string;
  transactions_imported: number;
  parse_warnings: string[];
  metadata: Record<string, unknown>;
}

export interface RecategorizeResponse {
  updated: number;
  category_sources: Record<string, number>;
  clean_description_sources: Record<string, number>;
}

// --- Dashboard types ---

export interface MonthSummaryForDashboard {
  month: string;
  tx_count: number;
  total_income: number;
  total_expenses: number;
  net_savings: number;
  drew_from_savings: boolean;
  savings_rate: number;
  min_balance: number;
  max_balance: number;
  last_balance: number | null;
  last_balance_date: string | null;
  leisure_spent: number;
  leisure_budget: number;
  leisure_remaining: number;
  days_of_data: number;
  first_date: string | null;
  last_date: string | null;
  // pace — only present for current partial month
  days_elapsed: number | null;
  days_in_month: number | null;
  projected_month_end_expenses: number | null;
  by_category: CategoryBreakdown[];
}

export interface DashboardData {
  last_transaction_date: string | null;
  days_since_last_update: number;
  primary_month: MonthSummaryForDashboard;
  secondary_month: MonthSummaryForDashboard | null;
  primary_is_current: boolean;
  health: HealthScore;
}

// --- API calls ---

export const api = {
  health: () => get<{ status: string; available_months: string[]; total_transactions: number }>("/health"),
  months: () => get<{ months: string[] }>("/months"),
  summary: (month: string) => get<MonthlySummary>(`/summary/${month}`),
  healthScore: () => get<HealthScore>("/health-score"),
  dashboard: () => get<DashboardData>("/dashboard"),
  transactions: (params?: { month?: string; category?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.month) qs.set("month", params.month);
    if (params?.category) qs.set("category", params.category);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return get<TransactionList>(`/transactions?${qs}`);
  },
  upload: (file: File, bank = "santander", useAi = false) => {
    const form = new FormData();
    form.append("file", file);
    form.append("bank", bank);
    form.append("use_ai", String(useAi));
    return post<UploadResponse>("/upload", form);
  },
  recategorize: (useAi = false) => {
    const form = new FormData();
    return post<RecategorizeResponse>(`/recategorize?use_ai=${useAi}`, form);
  },
};
