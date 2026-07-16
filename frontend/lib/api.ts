// lib/api.ts — typed API client for the FastAPI backend
//
// Authentication uses httpOnly cookies (set by the backend on login/register).
// All fetch calls include credentials: "include" so the browser sends the cookie
// automatically. No token storage in JS code — the cookie is invisible to JS.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Base fetch helpers — all include credentials for cookie-based auth
// ---------------------------------------------------------------------------

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    credentials: "include",
  });
  if (res.status === 401) throw new AuthError();
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${path} → ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: FormData | null): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    body: body ?? undefined,
    credentials: "include",
  });
  if (res.status === 401) throw new AuthError();
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${path} → ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (res.status === 401) throw new AuthError();
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API POST ${path} → ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (res.status === 401) throw new AuthError();
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API PATCH ${path} → ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (res.status === 401) throw new AuthError();
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API DELETE ${path} → ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth error — thrown when the server returns 401
// Components / middleware can catch this to redirect to /login
// ---------------------------------------------------------------------------

export class AuthError extends Error {
  constructor() {
    super("Not authenticated");
    this.name = "AuthError";
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
  total: number;       // total matching rows (unpaginated)
  amount_total: number; // sum of amount for all matching rows
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

// Alert is a RuleResult — same shape, just filtered to amber/red by the backend
export type Alert = RuleResult;

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

export interface PatchTransactionRequest {
  clean_description?: string | null;
  category?: string | null;
  subcategory?: string | null;
}

export interface PatchTransactionResponse {
  id: string;
  clean_description: string | null;
  clean_description_source: string | null;
  category: string | null;
  subcategory: string | null;
  category_source: string | null;
}

// --- Category types ---

export type CategoryRole = "needs" | "wants" | "leisure" | "fixed" | "subscriptions" | "savings" | "income" | "other";

export interface CategoryItem {
  id: string;
  name: string;
  parent_id: string | null;
  color: string | null;
  role: CategoryRole | null;
  position: number;
  created_at: string | null;
}

export interface CategoryWithChildren {
  id: string;
  name: string;
  color: string | null;
  role: CategoryRole | null;
  position: number;
  created_at: string | null;
  subcategories: CategoryItem[];
}

export interface CategoryListResponse {
  categories: CategoryWithChildren[];
}

export interface CategoryCreateRequest {
  id: string;
  name: string;
  parent_id?: string | null;
  color?: string | null;
  role?: CategoryRole | null;
  position?: number;
}

export interface CategoryUpdateRequest {
  name?: string | null;
  color?: string | null;
  role?: CategoryRole | null;
  position?: number | null;
}

export interface CategoryDeleteResponse {
  deleted_categories: number;
  affected_transactions: number;
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

// --- Health score history ---

export interface HealthScoreHistoryEntry {
  id: string;
  recorded_at: string;
  import_id: string | null;
  overall_score: number;
  grade: string;
  rule_scores: Record<string, number>;
}

export interface HealthScoreHistoryResponse {
  history: HealthScoreHistoryEntry[];
}

// --- Auth types ---

export interface UserOut {
  id: string;
  email: string;
  name: string | null;
  is_active: boolean;
}

export interface AuthResponse {
  message: string;
  user: UserOut;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export const api = {
  // --- Auth (no credentials needed for login/register — they set the cookie) ---
  login: (email: string, password: string) =>
    postJson<AuthResponse>("/auth/login", { email, password }),
  register: (email: string, password: string, name?: string) =>
    postJson<AuthResponse>("/auth/register", { email, password, name }),
  logout: () => post<{ message: string }>("/auth/logout", null),
  me: () => get<UserOut>("/auth/me"),

  // --- Finance endpoints (all require auth cookie) ---
  health: () => get<{ status: string; available_months: string[]; total_transactions: number }>("/health"),
  months: () => get<{ months: string[] }>("/months"),
  summary: (month: string) => get<MonthlySummary>(`/summary/${month}`),
  healthScore: () => get<HealthScore>("/health-score"),
  healthHistory: (limit = 50) => get<HealthScoreHistoryResponse>(`/health-history?limit=${limit}`),
  dashboard: () => get<DashboardData>("/dashboard"),
  transactions: (params?: { month?: string; year?: number; category?: string; subcategory?: string; sort_by?: string; sort_dir?: "asc" | "desc"; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.month) qs.set("month", params.month);
    if (params?.year) qs.set("year", String(params.year));
    if (params?.category) qs.set("category", params.category);
    if (params?.subcategory) qs.set("subcategory", params.subcategory);
    if (params?.sort_by) qs.set("sort_by", params.sort_by);
    if (params?.sort_dir) qs.set("sort_dir", params.sort_dir);
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.offset != null) qs.set("offset", String(params.offset));
    return get<TransactionList>(`/transactions?${qs}`);
  },
  upload: (file: File, bank = "santander", useAi = false) => {
    const form = new FormData();
    form.append("file", file);
    form.append("bank", bank);
    form.append("use_ai", String(useAi));
    return post<UploadResponse>("/upload", form);
  },
  recategorize: (useAi = false) =>
    post<RecategorizeResponse>(`/recategorize?use_ai=${useAi}`, null),
  patchTransaction: (id: string, data: PatchTransactionRequest) =>
    patchJson<PatchTransactionResponse>(`/transactions/${id}`, data),
  // Categories CRUD
  categories: () => get<CategoryListResponse>("/categories"),
  createCategory: (data: CategoryCreateRequest) =>
    postJson<CategoryItem>("/categories", data),
  updateCategory: (id: string, data: CategoryUpdateRequest) =>
    patchJson<CategoryItem>(`/categories/${id}`, data),
  deleteCategory: (id: string) =>
    del<CategoryDeleteResponse>(`/categories/${id}`),
};
