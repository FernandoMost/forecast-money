"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  PatchTransactionRequest,
  Transaction,
  TransactionList,
} from "@/lib/api";
import { formatEur } from "@/lib/utils";
import CategoryTree, {
  catLabel,
  CategorySelection,
  subLabel,
} from "@/components/CategoryTree";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 100;

const SOURCE_BADGE: Record<string, string> = {
  rule:   "bg-gray-100 text-gray-500",
  ai:     "bg-purple-100 text-purple-700",
  cache:  "bg-blue-100 text-blue-600",
  manual: "bg-amber-100 text-amber-700",
};

const MONTH_NAMES = [
  "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

// ---------------------------------------------------------------------------
// Year / Month filter bar
// ---------------------------------------------------------------------------

function YearMonthFilter({
  months,
  selectedYear,
  selectedMonth,
  onYearChange,
  onMonthChange,
}: {
  months: string[];
  selectedYear: number | null;
  selectedMonth: string | null;
  onYearChange: (y: number | null) => void;
  onMonthChange: (m: string | null) => void;
}) {
  const years = [...new Set(months.map((m) => parseInt(m.slice(0, 4))))].sort(
    (a, b) => b - a
  );

  const monthsForYear = selectedYear
    ? months.filter((m) => m.startsWith(String(selectedYear)))
    : [];

  function handleYear(y: number | null) {
    onYearChange(y);
    onMonthChange(null);
  }

  function handleMonth(m: string) {
    onMonthChange(selectedMonth === m ? null : m);
  }

  return (
    <div className="space-y-1.5">
      {/* Year row */}
      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => handleYear(null)}
          className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
            !selectedYear
              ? "bg-gray-800 text-white border-gray-800"
              : "bg-white text-gray-600 border-gray-300 hover:border-gray-500"
          }`}
        >
          All time
        </button>
        {years.map((y) => (
          <button
            key={y}
            type="button"
            onClick={() => handleYear(selectedYear === y ? null : y)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              selectedYear === y
                ? "bg-gray-800 text-white border-gray-800"
                : "bg-white text-gray-600 border-gray-300 hover:border-gray-500"
            }`}
          >
            {y}
          </button>
        ))}
      </div>

      {/* Month row — only when a year is selected */}
      {selectedYear && monthsForYear.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-2 border-l-2 border-gray-300">
          {monthsForYear.map((m) => {
            const mo = parseInt(m.slice(5, 7));
            return (
              <button
                key={m}
                type="button"
                onClick={() => handleMonth(m)}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  selectedMonth === m
                    ? "bg-gray-700 text-white border-gray-700"
                    : "bg-white text-gray-600 border-gray-300 hover:border-gray-500"
                }`}
              >
                {MONTH_NAMES[mo]}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edit form (renders inline below the row being edited)
// ---------------------------------------------------------------------------

function EditForm({
  tx,
  onSave,
  onCancel,
}: {
  tx: Transaction;
  onSave: (updated: Partial<Transaction>) => void;
  onCancel: () => void;
}) {
  const [desc, setDesc] = useState(tx.clean_description ?? tx.description);
  const [catSel, setCatSel] = useState<CategorySelection>({
    category: tx.category ?? null,
    subcategory: tx.subcategory ?? null,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const patch: PatchTransactionRequest = {
      clean_description: desc.trim() || null,
      category: catSel.category ?? undefined,
      subcategory: catSel.subcategory ?? undefined,
    };
    try {
      const result = await api.patchTransaction(tx.id, patch);
      onSave({
        clean_description: result.clean_description,
        clean_description_source: result.clean_description_source ?? undefined,
        category: result.category ?? undefined,
        subcategory: result.subcategory ?? undefined,
        category_source: result.category_source ?? undefined,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className="bg-indigo-50">
      <td colSpan={6} className="px-4 py-3">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="flex items-center gap-2 text-xs text-indigo-600 font-medium mb-1">
            <span>✏ Editing</span>
            <span className="text-gray-400 font-normal">{tx.date} · {tx.description}</span>
          </div>

          {/* Description */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500 font-medium">Clean description</label>
            <input
              ref={inputRef}
              type="text"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              className="w-full max-w-md border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              placeholder="Human-readable label…"
            />
          </div>

          {/* Category tree */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500 font-medium">Category</label>
            <CategoryTree selected={catSel} onChange={(cat, sub) => setCatSel({ category: cat, subcategory: sub })} />
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}

          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-1.5 bg-white text-gray-600 text-xs font-medium rounded-lg border border-gray-300 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </form>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Pagination controls
// ---------------------------------------------------------------------------

function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (newOffset: number) => void;
}) {
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-sm">
      <span className="text-gray-500 text-xs">
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <div className="flex gap-2">
        <button
          disabled={page <= 1}
          onClick={() => onChange(offset - limit)}
          className="px-3 py-1 rounded-lg border border-gray-300 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
        >
          ← Prev
        </button>
        <span className="px-3 py-1 text-xs text-gray-500">
          {page} / {totalPages}
        </span>
        <button
          disabled={page >= totalPages}
          onClick={() => onChange(offset + limit)}
          className="px-3 py-1 rounded-lg border border-gray-300 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
        >
          Next →
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function TransactionsPage() {
  const [months, setMonths] = useState<string[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [catFilter, setCatFilter] = useState<CategorySelection>({ category: null, subcategory: null });
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<TransactionList | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Load available months once
  useEffect(() => {
    api.months().then((d) => setMonths(d.months));
  }, []);

  // Reset pagination whenever filters change
  useEffect(() => {
    setOffset(0);
    setEditingId(null);
  }, [selectedYear, selectedMonth, catFilter]);

  // Fetch transactions
  const fetchTxs = useCallback(() => {
    setLoading(true);
    api.transactions({
      month: selectedMonth ?? undefined,
      year: (!selectedMonth && selectedYear) ? selectedYear : undefined,
      category: catFilter.category ?? undefined,
      subcategory: catFilter.subcategory ?? undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then(setData)
      .finally(() => setLoading(false));
  }, [selectedMonth, selectedYear, catFilter, offset]);

  useEffect(() => {
    fetchTxs();
  }, [fetchTxs]);

  function handleEdit(id: string) {
    setEditingId((prev) => (prev === id ? null : id));
  }

  function handleSave(txId: string, updated: Partial<Transaction>) {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((tx) =>
          tx.id === txId ? { ...tx, ...updated } : tx
        ),
      };
    });
    setEditingId(null);
  }

  // Summary label for active filters
  const filterLabel = [
    selectedMonth
      ? selectedMonth
      : selectedYear
      ? String(selectedYear)
      : "All time",
    catFilter.subcategory
      ? subLabel(catFilter.subcategory)
      : catFilter.category
      ? catLabel(catFilter.category)
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Transactions</h1>
        <p className="text-gray-500 text-sm mt-1">Filter, explore and annotate your spending.</p>
      </div>

      {/* ── Filters ── */}
      <div className="space-y-3 bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
        <div className="text-xs text-gray-400 uppercase tracking-wide font-medium">Period</div>
        <YearMonthFilter
          months={months}
          selectedYear={selectedYear}
          selectedMonth={selectedMonth}
          onYearChange={setSelectedYear}
          onMonthChange={setSelectedMonth}
        />
        <div className="text-xs text-gray-400 uppercase tracking-wide font-medium pt-1">Category</div>
        <CategoryTree
          selected={catFilter}
          onChange={(cat, sub) => setCatFilter({ category: cat, subcategory: sub })}
          showAll
        />
      </div>

      {/* ── Results header ── */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-600">
          {loading ? (
            <span className="text-gray-400">Loading…</span>
          ) : data ? (
            <>
              <span className="font-medium">{data.total.toLocaleString()}</span> transactions
              {filterLabel && <span className="text-gray-400"> — {filterLabel}</span>}
            </>
          ) : null}
        </span>
      </div>

      {/* ── Table ── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left font-medium text-gray-600 w-28">Date</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Description</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Category</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 w-32">Amount</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 w-32">Balance</th>
                <th className="px-4 py-3 w-10" aria-label="Edit" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-gray-400">
                    Loading…
                  </td>
                </tr>
              )}

              {!loading && data?.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-gray-400">
                    No transactions found for this filter.
                  </td>
                </tr>
              )}

              {!loading &&
                data?.items.map((tx) => {
                  const isIncome = tx.amount > 0 && !tx.is_reversal;
                  const isEditing = editingId === tx.id;

                  return (
                    <>
                      <tr
                        key={tx.id}
                        className={`group transition-colors ${
                          tx.is_reversal
                            ? "opacity-40"
                            : isIncome
                            ? "bg-green-50 hover:bg-green-100"
                            : isEditing
                            ? "bg-indigo-50"
                            : "hover:bg-gray-50"
                        }`}
                      >
                        <td className="px-4 py-2.5 text-gray-400 whitespace-nowrap text-xs">
                          {tx.date}
                        </td>
                        <td className="px-4 py-2.5 max-w-xs" title={tx.description}>
                          {tx.clean_description ? (
                            <span className={`font-medium ${isIncome ? "text-green-800" : "text-gray-900"}`}>
                              {tx.clean_description}
                            </span>
                          ) : (
                            <span className="text-gray-400 truncate block text-xs">
                              {tx.description}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          {tx.category ? (
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                isIncome
                                  ? "bg-green-100 text-green-800"
                                  : "bg-indigo-50 text-indigo-700"
                              }`}>
                                {tx.subcategory ? subLabel(tx.subcategory) : catLabel(tx.category)}
                              </span>
                              {tx.category_source && (
                                <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                                  SOURCE_BADGE[tx.category_source] ?? "bg-gray-100 text-gray-400"
                                }`}>
                                  {tx.category_source}
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                        <td className={`px-4 py-2.5 text-right font-medium tabular-nums whitespace-nowrap ${
                          isIncome ? "text-green-700 font-bold" : "text-gray-700"
                        }`}>
                          {formatEur(tx.amount)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums text-xs">
                          {formatEur(tx.balance)}
                        </td>
                        <td className="px-2 py-2.5 text-center">
                          <button
                            type="button"
                            onClick={() => handleEdit(tx.id)}
                            title="Edit transaction"
                            className={`p-1 rounded transition-colors ${
                              isEditing
                                ? "text-indigo-600 bg-indigo-100"
                                : "text-gray-300 hover:text-indigo-500 opacity-0 group-hover:opacity-100"
                            }`}
                          >
                            ✏
                          </button>
                        </td>
                      </tr>

                      {isEditing && (
                        <EditForm
                          key={`edit-${tx.id}`}
                          tx={tx}
                          onSave={(updated) => handleSave(tx.id, updated)}
                          onCancel={() => setEditingId(null)}
                        />
                      )}
                    </>
                  );
                })}
            </tbody>

            {/* Total footer */}
            {!loading && data && data.total > 0 && (
              <tfoot>
                <tr className="border-t-2 border-gray-200 bg-gray-50">
                  <td colSpan={3} className="px-4 py-2.5 text-xs text-gray-500">
                    Total for <span className="font-medium">{filterLabel || "all transactions"}</span>
                    {data.total > PAGE_SIZE && (
                      <span className="text-gray-400"> ({data.total.toLocaleString()} transactions)</span>
                    )}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-bold tabular-nums whitespace-nowrap text-sm ${
                    data.amount_total >= 0 ? "text-green-700" : "text-gray-800"
                  }`}>
                    {formatEur(data.amount_total)}
                  </td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            )}
          </table>
        </div>

        {/* Pagination */}
        {data && (
          <Pagination
            total={data.total}
            limit={PAGE_SIZE}
            offset={offset}
            onChange={setOffset}
          />
        )}
      </div>
    </div>
  );
}
