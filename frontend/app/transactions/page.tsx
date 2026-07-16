"use client";

import {
  ColumnDef,
  ColumnResizeMode,
  ColumnSizingState,
  VisibilityState,
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
  useCategoryTree,
  catLabel,
  CategorySelection,
  subLabel,
} from "@/components/CategoryTree";
import { useT } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 100;
const LS_KEY_SIZES      = "tx_col_sizes";
const LS_KEY_VISIBILITY = "tx_col_visibility";

// Columns that can be hidden (not date, amount — those are essential)
const HIDEABLE_COLUMNS = ["description", "category", "balance", "date"];

// Source badge: only rendered when source is NOT "rule"
const SOURCE_DOT: Record<string, { cls: string; label: string }> = {
  ai:     { cls: "bg-purple-400", label: "AI" },
  cache:  { cls: "bg-blue-400",   label: "Cached" },
  manual: { cls: "bg-amber-400",  label: "Manual" },
};

const MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

function lsGet<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch { return fallback; }
}

function lsSet(key: string, value: unknown) {
  if (typeof window === "undefined") return;
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* quota */ }
}

// ---------------------------------------------------------------------------
// Source dot badge
// ---------------------------------------------------------------------------

function SourceDot({ source }: { source: string | null | undefined }) {
  if (!source || source === "rule") return null;
  const dot = SOURCE_DOT[source];
  if (!dot) return null;
  return (
    <span title={dot.label} className={`inline-block w-1.5 h-1.5 rounded-full ${dot.cls} shrink-0`} />
  );
}

// ---------------------------------------------------------------------------
// Inline description editor
// Click on the description text → becomes an input + send button
// ---------------------------------------------------------------------------

function InlineDescEdit({
  tx,
  onSaved,
}: {
  tx: Transaction;
  onSaved: (updated: Partial<Transaction>) => void;
}) {
  const { t } = useT();
  const [editing, setEditing]   = useState(false);
  const [value, setValue]       = useState(tx.clean_description ?? "");
  const [saving, setSaving]     = useState(false);
  const inputRef                = useRef<HTMLInputElement>(null);
  const isIncome                = tx.amount > 0 && !tx.is_reversal;

  // sync if tx changes from outside (e.g. category patch that returns updated tx)
  useEffect(() => {
    if (!editing) setValue(tx.clean_description ?? "");
  }, [tx.clean_description, editing]);

  function open() {
    setValue(tx.clean_description ?? "");
    setEditing(true);
    // focus after state flushes
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  function cancel() {
    setEditing(false);
    setValue(tx.clean_description ?? "");
  }

  async function submit() {
    if (saving) return;
    setSaving(true);
    try {
      const result = await api.patchTransaction(tx.id, {
        clean_description: value.trim() || null,
      });
      onSaved({
        clean_description: result.clean_description,
        clean_description_source: result.clean_description_source ?? undefined,
      });
      setEditing(false);
    } catch {
      /* keep editing open on error */
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <div
        className="flex items-center gap-1.5 min-w-0 group/desc cursor-text"
        onClick={open}
        title={t("transactions.editLabelTooltip")}
      >
        {tx.clean_description ? (
          <span
            className={`font-medium truncate ${isIncome ? "text-green-800" : "text-gray-900 dark:text-white"} group-hover/desc:underline group-hover/desc:decoration-dotted`}
            title={tx.description}
          >
            {tx.clean_description}
          </span>
        ) : (
          <span
            className="text-gray-400 dark:text-gray-500 text-xs truncate group-hover/desc:text-gray-600 dark:group-hover/desc:text-gray-400"
            title={tx.description}
          >
            {tx.description}
          </span>
        )}
        <SourceDot source={tx.clean_description_source} />
      </div>
    );
  }

  return (
    <form
      className="flex items-center gap-1 min-w-0"
      onSubmit={(e) => { e.preventDefault(); submit(); }}
    >
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
        placeholder={tx.description}
        className="flex-1 min-w-0 border border-indigo-300 dark:border-indigo-600 rounded px-1.5 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-400 dark:focus:ring-indigo-500 bg-white dark:bg-gray-800 dark:text-white"
      />
      <button
        type="submit"
        disabled={saving}
        title={t("transactions.saveTitle")}
        className="p-0.5 rounded text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30 disabled:opacity-40 shrink-0"
      >
        {saving ? (
          <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
            <circle cx="12" cy="12" r="10" strokeOpacity={0.2} />
            <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" />
          </svg>
        ) : (
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
            <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Inline category editor
// Click on the category pill → becomes a <select> + confirm button
// ---------------------------------------------------------------------------

function InlineCatEdit({
  tx,
  onSaved,
}: {
  tx: Transaction;
  onSaved: (updated: Partial<Transaction>) => void;
}) {
  const { t } = useT();
  const { tree, catLabel: label, subLabel: slabel } = useCategoryTree();
  const [editing, setEditing]   = useState(false);
  const [saving, setSaving]     = useState(false);
  const isIncome                = tx.amount > 0 && !tx.is_reversal;

  // Encode current value as "cat/sub" or "cat/" or ""
  const currentEncoded = tx.category
    ? `${tx.category}/${tx.subcategory ?? ""}`
    : "";
  const [value, setValue] = useState(currentEncoded);

  // sync if tx changes
  useEffect(() => {
    if (!editing) setValue(currentEncoded);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tx.category, tx.subcategory, editing]);

  function open(e: React.MouseEvent) {
    e.stopPropagation();
    setValue(currentEncoded);
    setEditing(true);
  }

  function cancel() { setEditing(false); }

  async function submit(e: React.MouseEvent) {
    e.stopPropagation();
    if (saving) return;
    setSaving(true);
    const [cat, sub] = value.split("/");
    try {
      const result = await api.patchTransaction(tx.id, {
        category: cat || null,
        subcategory: sub || null,
      });
      onSaved({
        category: result.category ?? undefined,
        subcategory: result.subcategory ?? undefined,
        category_source: result.category_source ?? undefined,
      });
      setEditing(false);
    } catch {
      /* keep open */
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    if (!tx.category) {
      return (
        <span
          className="text-gray-300 dark:text-gray-600 text-xs cursor-pointer hover:text-indigo-400"
          onClick={open}
          title={t("transactions.setCategoryTitle")}
        >
          —
        </span>
      );
    }
    const catStr = label(tx.category);
    const subStr = tx.subcategory ? slabel(tx.subcategory) : null;
    return (
      <div className="flex items-center gap-1.5 min-w-0">
        <span
          onClick={open}
          title={t("transactions.editCategoryTitle")}
          className={`px-1.5 py-0.5 rounded-full text-xs font-medium truncate cursor-pointer hover:ring-1 hover:ring-indigo-300 transition-shadow ${
            isIncome ? "bg-green-100 text-green-800" : "bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300"
          }`}
        >
          {subStr ? (
            <>{catStr} <span className="opacity-50">·</span> {subStr}</>
          ) : catStr}
        </span>
        <SourceDot source={tx.category_source} />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1 min-w-0" onClick={(e) => e.stopPropagation()}>
      <select
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
        className="border border-indigo-300 dark:border-gray-600 rounded px-1 py-0.5 text-xs bg-white dark:bg-gray-800 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-400 dark:focus:ring-indigo-500 min-w-[140px] max-w-[200px]"
      >
        <option value="">{t("transactions.noneCategory")}</option>
        {Object.entries(tree).map(([cat, subs]) => (
          <optgroup key={cat} label={label(cat)}>
            <option value={`${cat}/`}>{label(cat)}</option>
            {subs.map((sub) => (
              <option key={sub} value={`${cat}/${sub}`}>
                {label(cat)} · {slabel(sub)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <button
        onClick={submit}
        disabled={saving}
        title={t("transactions.saveCategoryTitle")}
        className="p-0.5 rounded text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30 disabled:opacity-40 shrink-0"
      >
        {saving ? (
          <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
            <circle cx="12" cy="12" r="10" strokeOpacity={0.2} />
            <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" />
          </svg>
        ) : (
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
            <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); cancel(); }}
        title={t("transactions.cancelTitle")}
        className="p-0.5 rounded text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 shrink-0"
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
          <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
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
  const { t } = useT();
  const years = [...new Set(months.map((m) => parseInt(m.slice(0, 4))))].sort((a, b) => b - a);
  const monthsForYear = selectedYear ? months.filter((m) => m.startsWith(String(selectedYear))) : [];

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1.5">
        <Pill active={!selectedYear} onClick={() => { onYearChange(null); onMonthChange(null); }}>{t("transactions.allTime")}</Pill>
        {years.map((y) => (
          <Pill key={y} active={selectedYear === y} onClick={() => { onYearChange(selectedYear === y ? null : y); onMonthChange(null); }}>{y}</Pill>
        ))}
      </div>
      {selectedYear && monthsForYear.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-2 border-l-2 border-gray-300 dark:border-gray-600">
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
  const off = "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-gray-500 dark:hover:border-gray-400";
  return (
    <button type="button" onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${active ? on : off}`}>
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Column visibility toggle menu
// ---------------------------------------------------------------------------

function ColumnToggleMenu({
  table,
  onVisibilityChange,
}: {
  table: ReturnType<typeof useReactTable<Transaction>>;
  onVisibilityChange: (id: string, visible: boolean) => void;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const hideableCols = table.getAllLeafColumns().filter((c) => HIDEABLE_COLUMNS.includes(c.id));

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
        title="Show/hide columns"
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2v-4M9 21H5a2 2 0 0 1-2-2v-4m0 0h18" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        {t("transactions.columnsButton")}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-40 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg p-2 min-w-[140px]">
          {hideableCols.map((col) => {
            const visible = col.getIsVisible();
            const label = typeof col.columnDef.header === "string"
              ? col.columnDef.header
              : col.id.charAt(0).toUpperCase() + col.id.slice(1);
            return (
              <label
                key={col.id}
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer text-xs text-gray-700 dark:text-gray-300"
              >
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={(e) => {
                    col.toggleVisibility(e.target.checked);
                    onVisibilityChange(col.id, e.target.checked);
                  }}
                  className="accent-indigo-600"
                />
                {label}
              </label>
            );
          })}
        </div>
      )}
    </div>
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
  const { t } = useT();
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(data.total / PAGE_SIZE);

  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm shadow-[0_-2px_8px_rgba(0,0,0,0.06)]">
      <div className="max-w-6xl mx-auto px-6 py-2.5 flex items-center gap-4">
        <span className="text-xs text-gray-500 dark:text-gray-400 flex-1 min-w-0 truncate">
          <span className="font-semibold text-gray-800 dark:text-gray-200">{t("transactions.txCount", { count: data.total.toLocaleString() })}</span>
          {filterLabel && <span className="text-gray-400 dark:text-gray-500"> — {filterLabel}</span>}
        </span>
        <span className={`text-sm font-bold tabular-nums shrink-0 ${data.amount_total >= 0 ? "text-green-700" : "text-gray-800 dark:text-gray-200"}`}>
          {formatEur(data.amount_total)}
        </span>
        {totalPages > 1 && (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-xs text-gray-400 dark:text-gray-500">{offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)}</span>
            <button
              disabled={page <= 1}
              onClick={() => onPageChange(offset - PAGE_SIZE)}
              className="px-2.5 py-1 rounded-lg border border-gray-300 dark:border-gray-600 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
            >{t("transactions.prev")}</button>
            <span className="px-2 text-xs text-gray-500 dark:text-gray-400">{page} / {totalPages}</span>
            <button
              disabled={page >= totalPages}
              onClick={() => onPageChange(offset + PAGE_SIZE)}
              className="px-2.5 py-1 rounded-lg border border-gray-300 dark:border-gray-600 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
            >{t("transactions.next")}</button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

// Compute current year/month string for default filter
function getCurrentYearMonth(): { year: number; month: string } {
  const now = new Date();
  const year = now.getFullYear();
  const month = `${year}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  return { year, month };
}

export default function TransactionsPage() {
  const { t } = useT();
  const { year: currentYear, month: currentMonth } = getCurrentYearMonth();

  const [months, setMonths]             = useState<string[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(currentYear);
  const [selectedMonth, setSelectedMonth] = useState<string | null>(currentMonth);
  const [catFilter, setCatFilter]       = useState<CategorySelection>({ category: null, subcategory: null });
  const [sorting, setSorting]           = useState<SortingState>([{ id: "date", desc: true }]);
  const [offset, setOffset]             = useState(0);
  const [data, setData]                 = useState<TransactionList | null>(null);
  const [loading, setLoading]           = useState(false);

  // Column sizing — restored from localStorage
  const [columnSizing, setColumnSizing] = useState<ColumnSizingState>(
    () => lsGet<ColumnSizingState>(LS_KEY_SIZES, {})
  );

  // Column visibility — restored from localStorage
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(
    () => lsGet<VisibilityState>(LS_KEY_VISIBILITY, {})
  );

  // Load months on mount; if current month has no data, fall back to most recent
  useEffect(() => {
    api.months().then((d) => {
      setMonths(d.months);
      // If current month is in the list, keep the default; otherwise pick latest month
      if (d.months.length > 0 && !d.months.includes(currentMonth)) {
        const latest = d.months[0]; // DESC order
        const latestYear = parseInt(latest.slice(0, 4));
        setSelectedYear(latestYear);
        setSelectedMonth(latest);
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reset pagination on any filter or sort change
  useEffect(() => { setOffset(0); }, [selectedYear, selectedMonth, catFilter, sorting]);

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
  }

  // Persist column sizing to localStorage
  function handleColumnSizingChange(updater: ColumnSizingState | ((old: ColumnSizingState) => ColumnSizingState)) {
    setColumnSizing((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      lsSet(LS_KEY_SIZES, next);
      return next;
    });
  }

  // Persist visibility to localStorage
  function handleVisibilityChange(id: string, visible: boolean) {
    setColumnVisibility((prev) => {
      const next = { ...prev, [id]: visible };
      lsSet(LS_KEY_VISIBILITY, next);
      return next;
    });
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
      header: t("transactions.colDate"),
      size: 96,
      minSize: 72,
      enableSorting: true,
      cell: ({ row }) => (
        <span className="text-gray-400 dark:text-gray-500 whitespace-nowrap text-xs tabular-nums">{row.original.date}</span>
      ),
    },
    {
      id: "description",
      accessorKey: "description",
      header: t("transactions.colDescription"),
      size: 260,
      minSize: 120,
      enableSorting: true,
      cell: ({ row, table: tbl }) => {
        // Access the onSave callback passed via table meta
        const onSave = (tbl.options.meta as { onSave?: (id: string, u: Partial<Transaction>) => void })?.onSave;
        return (
          <InlineDescEdit
            tx={row.original}
            onSaved={(updated) => onSave?.(row.original.id, updated)}
          />
        );
      },
    },
    {
      id: "category",
      accessorKey: "category",
      header: t("transactions.colCategory"),
      size: 180,
      minSize: 100,
      enableSorting: true,
      cell: ({ row, table: tbl }) => {
        const onSave = (tbl.options.meta as { onSave?: (id: string, u: Partial<Transaction>) => void })?.onSave;
        return (
          <InlineCatEdit
            tx={row.original}
            onSaved={(updated) => onSave?.(row.original.id, updated)}
          />
        );
      },
    },
    {
      id: "amount",
      accessorKey: "amount",
      header: t("transactions.colAmount"),
      size: 110,
      minSize: 80,
      enableSorting: true,
      meta: { align: "right" },
      cell: ({ row }) => {
        const tx = row.original;
        const isIncome = tx.amount > 0 && !tx.is_reversal;
        return (
          <span className={`tabular-nums whitespace-nowrap font-medium ${isIncome ? "text-green-700 font-bold" : "text-gray-700 dark:text-gray-200"}`}>
            {formatEur(tx.amount)}
          </span>
        );
      },
    },
    {
      id: "balance",
      accessorKey: "balance",
      header: t("transactions.colBalance"),
      size: 110,
      minSize: 80,
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="tabular-nums text-gray-400 dark:text-gray-500 text-xs whitespace-nowrap">
          {formatEur(row.original.balance)}
        </span>
      ),
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [t]);

  // ---------------------------------------------------------------------------
  // TanStack Table instance
  // ---------------------------------------------------------------------------

  const columnResizeMode: ColumnResizeMode = "onChange";

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    columnResizeMode,
    state: {
      sorting,
      columnSizing,
      columnVisibility,
    },
    onSortingChange: setSorting,
    onColumnSizingChange: handleColumnSizingChange as Parameters<typeof useReactTable<Transaction>>[0]["onColumnSizingChange"],
    onColumnVisibilityChange: (updater) => {
      setColumnVisibility((prev) => {
        const next = typeof updater === "function" ? updater(prev) : updater;
        lsSet(LS_KEY_VISIBILITY, next);
        return next;
      });
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: true,
    defaultColumn: { minSize: 60 },
    meta: { onSave: handleSave },
  });

  const colCount = table.getVisibleLeafColumns().length;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-4 pb-16">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("transactions.title")}</h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">{t("transactions.subtitle")}</p>
        </div>
        {/* Column visibility toggle — top right */}
        <div className="pt-1">
          <ColumnToggleMenu table={table} onVisibilityChange={handleVisibilityChange} />
        </div>
      </div>

      {/* Filters */}
      <div className="space-y-3 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
        <div className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wide font-medium">{t("transactions.periodLabel")}</div>
        <YearMonthFilter
          months={months}
          selectedYear={selectedYear}
          selectedMonth={selectedMonth}
          onYearChange={setSelectedYear}
          onMonthChange={setSelectedMonth}
        />
        <div className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wide font-medium pt-1">{t("transactions.categoryLabel")}</div>
        <CategoryTree
          selected={catFilter}
          onChange={(cat, sub) => setCatFilter({ category: cat, subcategory: sub })}
          showAll
        />
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table
            style={{ width: "100%", minWidth: table.getTotalSize(), tableLayout: "fixed" }}
            className="text-sm"
          >
            <colgroup>
              {table.getVisibleLeafColumns().map((col) => (
                <col key={col.id} style={{ width: col.getSize() }} />
              ))}
            </colgroup>

            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                  {hg.headers.map((header) => {
                    const isRight = (header.column.columnDef.meta as { align?: string } | undefined)?.align === "right";
                    const canSort = header.column.getCanSort();
                    const sorted  = header.column.getIsSorted();
                    return (
                      <th
                        key={header.id}
                        style={{ width: header.getSize(), position: "relative" }}
                        className={`px-2 py-2.5 font-medium text-gray-600 dark:text-gray-300 text-xs select-none border-r border-gray-200 dark:border-gray-700 last:border-r-0 ${isRight ? "text-right" : "text-left"} ${canSort ? "cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800" : ""}`}
                        onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                      >
                        <span className="inline-flex items-center gap-1">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {canSort && (
                            <span className="inline-flex flex-col leading-none text-[9px] -space-y-px">
                              <span className={sorted === "asc" ? "text-indigo-600" : "text-gray-300 dark:text-gray-600"}>▲</span>
                              <span className={sorted === "desc" ? "text-indigo-600" : "text-gray-300 dark:text-gray-600"}>▼</span>
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
                              header.column.getIsResizing() ? "bg-indigo-400" : "bg-gray-200 dark:bg-gray-700 hover:bg-indigo-300"
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

            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {loading && (
                <tr>
                  <td colSpan={colCount} className="px-2 py-10 text-center text-gray-400 dark:text-gray-500">{t("transactions.loading")}</td>
                </tr>
              )}
              {!loading && (data?.items.length === 0) && (
                <tr>
                  <td colSpan={colCount} className="px-2 py-10 text-center text-gray-400 dark:text-gray-500">
                    {t("transactions.empty")}
                  </td>
                </tr>
              )}
              {!loading && table.getRowModel().rows.map((row) => {
                const tx = row.original;
                const isIncome = tx.amount > 0 && !tx.is_reversal;
                return (
                  <tr
                    key={row.id}
                    className={`transition-colors ${
                      tx.is_reversal
                        ? "opacity-40"
                        : isIncome
                        ? "bg-green-50 dark:bg-green-950/30 hover:bg-green-100 dark:hover:bg-green-900/30"
                        : "hover:bg-gray-50 dark:hover:bg-gray-800"
                    }`}
                  >
                    {row.getVisibleCells().map((cell) => {
                      const isRight = (cell.column.columnDef.meta as { align?: string } | undefined)?.align === "right";
                      return (
                        <td
                          key={cell.id}
                          style={{ width: cell.column.getSize() }}
                          className={`px-2 py-2 overflow-hidden border-r border-gray-100 dark:border-gray-800 last:border-r-0 ${isRight ? "text-right" : ""}`}
                        >
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      );
                    })}
                  </tr>
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
