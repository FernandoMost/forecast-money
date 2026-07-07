"use client";

import {
  ColumnDef,
  ColumnResizeMode,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, PatchTransactionRequest, Transaction, TransactionList } from "@/lib/api";
import { formatEur } from "@/lib/utils";
import CategoryTree, {
  CATEGORY_TREE,
  catLabel,
  CategorySelection,
  subLabel,
} from "@/components/CategoryTree";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 100;

// Source badge: only rendered when source is NOT "rule" (rule is the default/silent path)
const SOURCE_DOT: Record<string, { cls: string; label: string }> = {
  ai:     { cls: "bg-purple-400", label: "AI" },
  cache:  { cls: "bg-blue-400",   label: "Cached" },
  manual: { cls: "bg-amber-400",  label: "Manual" },
};

const MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ---------------------------------------------------------------------------
// Source dot badge — only for non-default sources
// ---------------------------------------------------------------------------

function SourceDot({ source }: { source: string | null | undefined }) {
  if (!source || source === "rule") return null;
  const dot = SOURCE_DOT[source];
  if (!dot) return null;
  return (
    <span
      title={dot.label}
      className={`inline-block w-1.5 h-1.5 rounded-full ${dot.cls} shrink-0`}
    />
  );
}

// ---------------------------------------------------------------------------
// Year / Month filter bar
// ---------------------------------------------------------------------------

function YearMonthFilter({
  months, selectedYear, selectedMonth, onYearChange, onMonthChange,
}: {
  months: string[];
  selectedYear: number | null;
  selectedMonth: string | null;
  onYearChange: (y: number | null) => void;
  onMonthChange: (m: string | null) => void;
}) {
  const years = [...new Set(months.map((m) => parseInt(m.slice(0, 4))))].sort((a, b) => b - a);
  const monthsForYear = selectedYear ? months.filter((m) => m.startsWith(String(selectedYear))) : [];

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1.5">
        <Pill active={!selectedYear} onClick={() => { onYearChange(null); onMonthChange(null); }}>All time</Pill>
        {years.map((y) => (
          <Pill key={y} active={selectedYear === y} onClick={() => { onYearChange(selectedYear === y ? null : y); onMonthChange(null); }}>{y}</Pill>
        ))}
      </div>
      {selectedYear && monthsForYear.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-2 border-l-2 border-gray-300">
          {monthsForYear.map((m) => (
            <Pill key={m} active={selectedMonth === m} variant="gray"
              onClick={() => onMonthChange(selectedMonth === m ? null : m)}>
              {MONTH_NAMES[parseInt(m.slice(5, 7))]}
            </Pill>
          ))}
        </div>
      )}
    </div>
  );
}

function Pill({ active, onClick, children, variant = "dark" }: {
  active: boolean; onClick: () => void; children: React.ReactNode; variant?: "dark" | "gray";
}) {
  const on  = variant === "dark" ? "bg-gray-800 text-white border-gray-800" : "bg-gray-700 text-white border-gray-700";
  const off = "bg-white text-gray-600 border-gray-300 hover:border-gray-500";
  return (
    <button type="button" onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${active ? on : off}`}>
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Category select — <select> with <optgroup> per category
// Used in the inline edit form
// ---------------------------------------------------------------------------

function CategorySelect({
  value, onChange,
}: {
  value: CategorySelection;
  onChange: (sel: CategorySelection) => void;
}) {
  // Encode as "category/subcategory" or "category/"
  const encoded = value.category
    ? `${value.category}/${value.subcategory ?? ""}`
    : "";

  function handleChange(raw: string) {
    if (!raw) { onChange({ category: null, subcategory: null }); return; }
    const [cat, sub] = raw.split("/");
    onChange({ category: cat, subcategory: sub || null });
  }

  return (
    <select
      value={encoded}
      onChange={(e) => handleChange(e.target.value)}
      className="border border-gray-300 rounded-lg px-2 py-1 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 min-w-[180px]"
    >
      <option value="">— category —</option>
      {Object.entries(CATEGORY_TREE).map(([cat, subs]) => (
        <optgroup key={cat} label={catLabel(cat)}>
          <option value={`${cat}/`}>{catLabel(cat)} (all)</option>
          {subs.map((sub) => (
            <option key={sub} value={`${cat}/${sub}`}>
              {catLabel(cat)} · {subLabel(sub)}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// Inline edit form — compact single row
// ---------------------------------------------------------------------------

function EditRow({
  tx, colCount, onSave, onCancel,
}: {
  tx: Transaction;
  colCount: number;
  onSave: (updated: Partial<Transaction>) => void;
  onCancel: () => void;
}) {
  const [desc, setDesc] = useState(tx.clean_description ?? "");
  const [catSel, setCatSel] = useState<CategorySelection>({
    category: tx.category ?? null,
    subcategory: tx.subcategory ?? null,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

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
      setSaving(false);
    }
  }

  return (
    <tr className="bg-indigo-50 border-l-4 border-indigo-400">
      <td colSpan={colCount} className="px-4 py-2">
        <form onSubmit={handleSubmit}>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Description input */}
            <input
              ref={inputRef}
              type="text"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder={tx.description}
              className="flex-1 min-w-[160px] max-w-xs border border-gray-300 rounded-lg px-3 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />

            {/* Category select */}
            <CategorySelect value={catSel} onChange={setCatSel} />

            {error && <span className="text-xs text-red-600">{error}</span>}

            {/* Save */}
            <button
              type="submit"
              disabled={saving}
              title="Save"
              className="p-1.5 rounded-lg bg-green-100 text-green-700 hover:bg-green-200 disabled:opacity-40 transition-colors"
            >
              {saving ? (
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <circle cx="12" cy="12" r="10" strokeOpacity={0.25} />
                  <path d="M12 2a10 10 0 0 1 10 10" />
                </svg>
              ) : (
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                  <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </button>

            {/* Cancel */}
            <button
              type="button"
              onClick={onCancel}
              title="Cancel"
              className="p-1.5 rounded-lg bg-gray-100 text-gray-500 hover:bg-gray-200 transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </form>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Sticky bottom bar — total + pagination
// ---------------------------------------------------------------------------

function StickyBar({
  data, filterLabel, offset, onPageChange,
}: {
  data: TransactionList;
  filterLabel: string;
  offset: number;
  onPageChange: (o: number) => void;
}) {
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(data.total / PAGE_SIZE);

  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-gray-200 bg-white/95 backdrop-blur-sm shadow-[0_-2px_8px_rgba(0,0,0,0.06)]">
      <div className="max-w-6xl mx-auto px-6 py-2.5 flex items-center gap-4">
        {/* Left: count + filter */}
        <span className="text-xs text-gray-500 flex-1 min-w-0 truncate">
          <span className="font-semibold text-gray-800">{data.total.toLocaleString()}</span> transactions
          {filterLabel && <span className="text-gray-400"> — {filterLabel}</span>}
        </span>

        {/* Center: total amount */}
        <span className={`text-sm font-bold tabular-nums shrink-0 ${data.amount_total >= 0 ? "text-green-700" : "text-gray-800"}`}>
          {formatEur(data.amount_total)}
        </span>

        {/* Right: pagination */}
        {totalPages > 1 && (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-xs text-gray-400">{offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)}</span>
            <button
              disabled={page <= 1}
              onClick={() => onPageChange(offset - PAGE_SIZE)}
              className="px-2.5 py-1 rounded-lg border border-gray-300 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >← Prev</button>
            <span className="px-2 text-xs text-gray-500">{page} / {totalPages}</span>
            <button
              disabled={page >= totalPages}
              onClick={() => onPageChange(offset + PAGE_SIZE)}
              className="px-2.5 py-1 rounded-lg border border-gray-300 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >Next →</button>
          </div>
        )}
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
  const [sorting, setSorting] = useState<SortingState>([{ id: "date", desc: true }]);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<TransactionList | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  useEffect(() => { api.months().then((d) => setMonths(d.months)); }, []);

  // Reset pagination on any filter or sort change
  useEffect(() => { setOffset(0); setEditingId(null); }, [selectedYear, selectedMonth, catFilter, sorting]);

  const fetchTxs = useCallback(() => {
    const s = sorting[0];
    setLoading(true);
    api.transactions({
      month: selectedMonth ?? undefined,
      year: (!selectedMonth && selectedYear) ? selectedYear : undefined,
      category: catFilter.category ?? undefined,
      subcategory: catFilter.subcategory ?? undefined,
      sort_by: s?.id ?? "date",
      sort_dir: s ? (s.desc ? "desc" : "asc") : "desc",
      limit: PAGE_SIZE,
      offset,
    }).then(setData).finally(() => setLoading(false));
  }, [selectedMonth, selectedYear, catFilter, sorting, offset]);

  useEffect(() => { fetchTxs(); }, [fetchTxs]);

  function handleSave(txId: string, updated: Partial<Transaction>) {
    setData((prev) => prev
      ? { ...prev, items: prev.items.map((tx) => tx.id === txId ? { ...tx, ...updated } : tx) }
      : prev
    );
    setEditingId(null);
  }

  const filterLabel = [
    selectedMonth ?? (selectedYear ? String(selectedYear) : null),
    catFilter.subcategory ? subLabel(catFilter.subcategory) : catFilter.category ? catLabel(catFilter.category) : null,
  ].filter(Boolean).join(" · ");

  // ---------------------------------------------------------------------------
  // Column definitions
  // ---------------------------------------------------------------------------

  const columns = useMemo<ColumnDef<Transaction>[]>(() => [
    {
      id: "date",
      accessorKey: "date",
      header: "Date",
      size: 100,
      minSize: 80,
      enableSorting: true,
      cell: ({ row }) => (
        <span className="text-gray-400 whitespace-nowrap text-xs">{row.original.date}</span>
      ),
    },
    {
      id: "description",
      accessorKey: "description",
      header: "Description",
      size: 280,
      minSize: 120,
      enableSorting: true,
      cell: ({ row }) => {
        const tx = row.original;
        const isIncome = tx.amount > 0 && !tx.is_reversal;
        return (
          <div className="flex items-center gap-1.5 min-w-0">
            {tx.clean_description ? (
              <span className={`font-medium truncate ${isIncome ? "text-green-800" : "text-gray-900"}`}
                title={tx.description}>
                {tx.clean_description}
              </span>
            ) : (
              <span className="text-gray-400 text-xs truncate" title={tx.description}>
                {tx.description}
              </span>
            )}
            <SourceDot source={tx.clean_description_source} />
          </div>
        );
      },
    },
    {
      id: "category",
      accessorKey: "category",
      header: "Category",
      size: 180,
      minSize: 100,
      enableSorting: true,
      cell: ({ row }) => {
        const tx = row.original;
        const isIncome = tx.amount > 0 && !tx.is_reversal;
        if (!tx.category) return <span className="text-gray-300 text-xs">—</span>;

        const catStr = catLabel(tx.category);
        const subStr = tx.subcategory ? subLabel(tx.subcategory) : null;

        return (
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-medium truncate ${
                isIncome ? "bg-green-100 text-green-800" : "bg-indigo-50 text-indigo-700"
              }`}
              title={subStr ? `${catStr} · ${subStr}` : catStr}
            >
              {subStr ? (
                <>{catStr} <span className="opacity-50">·</span> {subStr}</>
              ) : catStr}
            </span>
            <SourceDot source={tx.category_source} />
          </div>
        );
      },
    },
    {
      id: "amount",
      accessorKey: "amount",
      header: "Amount",
      size: 120,
      minSize: 90,
      enableSorting: true,
      meta: { align: "right" },
      cell: ({ row }) => {
        const tx = row.original;
        const isIncome = tx.amount > 0 && !tx.is_reversal;
        return (
          <span className={`tabular-nums whitespace-nowrap font-medium ${isIncome ? "text-green-700 font-bold" : "text-gray-700"}`}>
            {formatEur(tx.amount)}
          </span>
        );
      },
    },
    {
      id: "balance",
      accessorKey: "balance",
      header: "Balance",
      size: 120,
      minSize: 90,
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="tabular-nums text-gray-400 text-xs whitespace-nowrap">
          {formatEur(row.original.balance)}
        </span>
      ),
    },
    {
      id: "_edit",
      header: "",
      size: 44,
      minSize: 44,
      enableResizing: false,
      enableSorting: false,
      cell: ({ row }) => {
        const isEditing = editingId === row.original.id;
        return (
          <button
            type="button"
            onClick={() => setEditingId((p) => (p === row.original.id ? null : row.original.id))}
            title="Edit"
            className={`p-1.5 rounded-md transition-colors ${
              isEditing
                ? "text-indigo-600 bg-indigo-100"
                : "text-gray-400 hover:text-indigo-600 hover:bg-indigo-50"
            }`}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        );
      },
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [editingId]);

  // ---------------------------------------------------------------------------
  // TanStack Table instance
  // ---------------------------------------------------------------------------

  const columnResizeMode: ColumnResizeMode = "onChange";

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    columnResizeMode,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: true,          // sorting is handled server-side
    state: { sorting },
    onSortingChange: setSorting,
    defaultColumn: { minSize: 60 },
  });

  const colCount = table.getAllLeafColumns().length;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    // pb-16 reserves space so sticky bar never covers last row
    <div className="space-y-5 pb-16">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Transactions</h1>
        <p className="text-gray-500 text-sm mt-1">Filter, explore and annotate your spending.</p>
      </div>

      {/* Filters */}
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

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          {/* minWidth = sum of column sizes so resize never compresses below initial sizes;
              width 100% fills the container when there's room to spare */}
          <table
            style={{ width: "100%", minWidth: table.getTotalSize(), tableLayout: "fixed" }}
            className="text-sm"
          >
            {/* colgroup drives widths */}
            <colgroup>
              {table.getVisibleLeafColumns().map((col) => (
                <col key={col.id} style={{ width: col.getSize() }} />
              ))}
            </colgroup>

            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="bg-gray-50 border-b border-gray-200">
                  {hg.headers.map((header) => {
                    const isRight = (header.column.columnDef.meta as { align?: string } | undefined)?.align === "right";
                    const canSort = header.column.getCanSort();
                    const sorted = header.column.getIsSorted(); // false | "asc" | "desc"
                    return (
                      <th
                        key={header.id}
                        style={{ width: header.getSize(), position: "relative" }}
                        className={`px-4 py-3 font-medium text-gray-600 text-xs select-none border-r border-gray-200 last:border-r-0 ${isRight ? "text-right" : "text-left"} ${canSort ? "cursor-pointer hover:bg-gray-100" : ""}`}
                        onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                      >
                        <span className="inline-flex items-center gap-1">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {canSort && (
                            <span className="inline-flex flex-col leading-none text-[9px] -space-y-px">
                              <span className={sorted === "asc" ? "text-indigo-600" : "text-gray-300"}>▲</span>
                              <span className={sorted === "desc" ? "text-indigo-600" : "text-gray-300"}>▼</span>
                            </span>
                          )}
                        </span>

                        {/* Resize handle */}
                        {header.column.getCanResize() && (
                          <div
                            onMouseDown={header.getResizeHandler()}
                            onTouchStart={header.getResizeHandler()}
                            onClick={(e) => e.stopPropagation()}
                            className={`absolute right-0 top-0 h-full w-1 cursor-col-resize select-none touch-none ${
                              header.column.getIsResizing()
                                ? "bg-indigo-400"
                                : "bg-gray-200 hover:bg-indigo-300"
                            }`}
                            style={{ transform: "translateX(50%)" }}
                          />
                        )}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>

            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr>
                  <td colSpan={colCount} className="px-4 py-10 text-center text-gray-400">
                    Loading…
                  </td>
                </tr>
              )}

              {!loading && (data?.items.length === 0) && (
                <tr>
                  <td colSpan={colCount} className="px-4 py-10 text-center text-gray-400">
                    No transactions found for this filter.
                  </td>
                </tr>
              )}

              {!loading && table.getRowModel().rows.map((row) => {
                const tx = row.original;
                const isIncome = tx.amount > 0 && !tx.is_reversal;
                const isEditing = editingId === tx.id;

                return (
                  <>
                    <tr
                      key={row.id}
                      className={`group transition-colors ${
                        tx.is_reversal
                          ? "opacity-40"
                          : isIncome
                          ? "bg-green-50 hover:bg-green-100"
                          : isEditing
                          ? "bg-indigo-50/60"
                          : "hover:bg-gray-50"
                      }`}
                    >
                      {row.getVisibleCells().map((cell) => {
                        const isRight = (cell.column.columnDef.meta as { align?: string } | undefined)?.align === "right";
                        return (
                          <td
                            key={cell.id}
                            style={{ width: cell.column.getSize() }}
                            className={`px-4 py-2.5 overflow-hidden border-r border-gray-100 last:border-r-0 ${isRight ? "text-right" : ""}`}
                          >
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        );
                      })}
                    </tr>

                    {isEditing && (
                      <EditRow
                        key={`edit-${tx.id}`}
                        tx={tx}
                        colCount={colCount}
                        onSave={(updated) => handleSave(tx.id, updated)}
                        onCancel={() => setEditingId(null)}
                      />
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Sticky bottom bar */}
      {!loading && data && data.total > 0 && (
        <StickyBar
          data={data}
          filterLabel={filterLabel ?? ""}
          offset={offset}
          onPageChange={setOffset}
        />
      )}
    </div>
  );
}
