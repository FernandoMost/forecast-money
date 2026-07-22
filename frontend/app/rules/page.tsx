"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  api,
  DescriptionRule,
  SuggestionGroup,
  SuggestionsResponse,
  RuleListResponse,
  StripConfigEntry,
  StripSuggestion,
  Transaction,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { formatDate, formatEur } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function PatternTag({
  value,
  onRemove,
}: {
  value: string;
  onRemove?: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 text-xs font-mono px-2 py-0.5 rounded">
      {value}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="text-gray-400 hover:text-red-500 ml-0.5 leading-none"
          aria-label="Remove pattern"
        >
          ×
        </button>
      )}
    </span>
  );
}

function StatusBadge({ n }: { n: number }) {
  if (n === 0)
    return (
      <span className="text-xs text-gray-400 dark:text-gray-500">0</span>
    );
  return (
    <span className="text-xs bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded-full font-medium">
      {n}
    </span>
  );
}

// ---------------------------------------------------------------------------
// PatternInput — controlled input that adds a tag on Enter or comma
// ---------------------------------------------------------------------------

function PatternInput({
  patterns,
  onChange,
  onEnterEmpty,
  inputRef,
}: {
  patterns: string[];
  onChange: (p: string[]) => void;
  onEnterEmpty?: () => void;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}) {
  const { t } = useT();
  const [draft, setDraft] = useState("");

  function commit() {
    const val = draft.trim();
    if (val && !patterns.includes(val)) {
      onChange([...patterns, val]);
    }
    setDraft("");
  }

  return (
    <div className="flex flex-wrap gap-1 items-center border border-gray-300 dark:border-gray-600 rounded px-2 py-1 min-h-[2rem] bg-white dark:bg-gray-800 focus-within:ring-1 ring-indigo-500">
      {patterns.map((p, i) => (
        <PatternTag
          key={i}
          value={p}
          onRemove={() => onChange(patterns.filter((_, j) => j !== i))}
        />
      ))}
      <input
        ref={inputRef}
        className="flex-1 min-w-[6rem] bg-transparent outline-none text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400"
        placeholder={t("rulesPage.patternPlaceholder")}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            if (draft.trim()) {
              commit();
            } else if (e.key === "Enter" && onEnterEmpty) {
              onEnterEmpty();
            }
          }
          if (e.key === "Backspace" && draft === "" && patterns.length) {
            onChange(patterns.slice(0, -1));
          }
        }}
        onBlur={commit}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// RuleTransactions — paginated list of transactions matching a rule
// ---------------------------------------------------------------------------

const PAGE_SIZE = 10;

function RuleTransactions({ label }: { label: string }) {
  const { t } = useT();
  const [page, setPage] = useState(0);
  const [items, setItems] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .transactions({
        clean_description: label,
        sort_by: "date",
        sort_dir: "desc",
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }, [label, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="border-t border-indigo-100 dark:border-indigo-900/40 bg-indigo-50/40 dark:bg-indigo-950/20 px-4 py-3">
      {loading ? (
        <p className="text-xs text-gray-400 py-2">{t("rulesPage.loading")}</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-gray-400 py-2">{t("rulesPage.ruleTxNoMatches")}</p>
      ) : (
        <>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <th className="text-left pb-1.5 font-medium">{t("rulesPage.ruleTxDate")}</th>
                <th className="text-right pb-1.5 font-medium">{t("rulesPage.ruleTxAmount")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((tx) => (
                <tr
                  key={tx.id}
                  className="border-b border-gray-100 dark:border-gray-800 last:border-0 hover:bg-white/60 dark:hover:bg-gray-800/30"
                >
                  <td className="py-1.5 text-gray-600 dark:text-gray-300">{formatDate(tx.date)}</td>
                  <td className={`py-1.5 text-right font-mono font-medium ${tx.amount < 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>
                    {formatEur(tx.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t("rulesPage.ruleTxPrev")}
              </button>
              <span className="text-xs text-gray-400">
                {t("rulesPage.ruleTxPage")
                  .replace("{page}", String(page + 1))
                  .replace("{total}", String(totalPages))}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t("rulesPage.ruleTxNext")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// RuleRow — existing rule with inline edit
// ---------------------------------------------------------------------------

function RuleRow({
  rule,
  onSaved,
  onDeleted,
}: {
  rule: DescriptionRule;
  onSaved: (updated: DescriptionRule) => void;
  onDeleted: (label: string) => void;
}) {
  const { t } = useT();
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [label, setLabel] = useState(rule.label);
  const [patterns, setPatterns] = useState<string[]>(rule.patterns);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function cancel() {
    setLabel(rule.label);
    setPatterns(rule.patterns);
    setEditing(false);
    setError(null);
  }

  async function save() {
    if (!patterns.length) {
      setError(t("rulesPage.errorNeedsPattern"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateDescriptionRule(rule.label, {
        new_label: label !== rule.label ? label : undefined,
        patterns,
      });
      onSaved(updated);
      setEditing(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!confirm(t("rulesPage.confirmDelete").replace("{label}", rule.label))) return;
    try {
      await api.deleteDescriptionRule(rule.label);
      onDeleted(rule.label);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  if (!editing) {
    return (
      <div className="border-b border-gray-100 dark:border-gray-800 last:border-0">
        <div
          className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-800/50 group cursor-pointer select-none"
          onClick={() => setExpanded((v) => !v)}
        >
          <span className="text-gray-300 dark:text-gray-600 shrink-0 w-3 text-center text-xs">
            {expanded ? "▾" : "▸"}
          </span>
          <StatusBadge n={rule.match_count} />
          <span className="font-medium text-sm text-gray-800 dark:text-gray-100 w-44 shrink-0 truncate">
            {rule.label}
          </span>
          <div className="flex flex-wrap gap-1 flex-1 min-w-0">
            {rule.patterns.map((p, i) => (
              <PatternTag key={i} value={p} />
            ))}
          </div>
          <div
            className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setEditing(true)}
              className="text-xs px-2 py-1 rounded text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              {t("rulesPage.edit")}
            </button>
            <button
              onClick={remove}
              className="text-xs px-2 py-1 rounded text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              {t("rulesPage.delete")}
            </button>
          </div>
        </div>
        {expanded && rule.match_count > 0 && <RuleTransactions label={rule.label} />}
      </div>
    );
  }

  return (
    <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 bg-indigo-50/30 dark:bg-indigo-900/10">
      <div className="flex flex-col gap-2">
        <div className="flex gap-2 items-center">
          <label className="text-xs text-gray-500 w-16 shrink-0">{t("rulesPage.label")}</label>
          <input
            className="flex-1 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <div className="flex gap-2 items-start">
          <label className="text-xs text-gray-500 w-16 shrink-0 pt-1.5">{t("rulesPage.patterns")}</label>
          <div className="flex-1">
            <PatternInput patterns={patterns} onChange={setPatterns} />
            <p className="text-xs text-gray-400 mt-1">{t("rulesPage.patternHint")}</p>
          </div>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button
            onClick={cancel}
            className="text-xs px-3 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            {t("rulesPage.cancel")}
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="text-xs px-3 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? t("rulesPage.saving") : t("rulesPage.save")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NewRuleForm — inline form to add a rule at the end of the list
// ---------------------------------------------------------------------------

function NewRuleForm({ onSaved }: { onSaved: (rule: DescriptionRule) => void }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState("");
  const [patterns, setPatterns] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!label.trim()) { setError(t("rulesPage.errorNeedsLabel")); return; }
    if (!patterns.length) { setError(t("rulesPage.errorNeedsPattern")); return; }
    setSaving(true);
    setError(null);
    try {
      const rule = await api.createDescriptionRule(label.trim(), patterns);
      onSaved(rule);
      setLabel("");
      setPatterns([]);
      setOpen(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full text-left px-4 py-2.5 text-sm text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 border-t border-gray-100 dark:border-gray-800"
      >
        + {t("rulesPage.addRule")}
      </button>
    );
  }

  return (
    <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800 bg-indigo-50/30 dark:bg-indigo-900/10">
      <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">{t("rulesPage.addRule")}</p>
      <div className="flex flex-col gap-2">
        <div className="flex gap-2 items-center">
          <label className="text-xs text-gray-500 w-16 shrink-0">{t("rulesPage.label")}</label>
          <input
            className="flex-1 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            placeholder={t("rulesPage.labelPlaceholder")}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") save(); }}
          />
        </div>
        <div className="flex gap-2 items-start">
          <label className="text-xs text-gray-500 w-16 shrink-0 pt-1.5">{t("rulesPage.patterns")}</label>
          <div className="flex-1">
            <PatternInput patterns={patterns} onChange={setPatterns} />
            <p className="text-xs text-gray-400 mt-1">{t("rulesPage.patternHint")}</p>
          </div>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => { setOpen(false); setError(null); }}
            className="text-xs px-3 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            {t("rulesPage.cancel")}
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="text-xs px-3 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? t("rulesPage.saving") : t("rulesPage.save")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SuggestionCard — one suggestion group
// Compact (inline) when there's only 1 distinct description, expanded otherwise.
// ---------------------------------------------------------------------------

function SuggestionCard({
  group,
  onApplied,
  onDismissed,
}: {
  group: SuggestionGroup;
  onApplied: (label: string) => void;
  onDismissed: (canonical: string) => void;
}) {
  const { t } = useT();
  const [label, setLabel] = useState(group.suggested_label);
  const [patterns, setPatterns] = useState<string[]>(group.suggested_patterns);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const patternInputRef = useRef<HTMLInputElement>(null);

  async function apply() {
    if (!label.trim()) { setError(t("rulesPage.errorNeedsLabel")); return; }
    if (!patterns.length) { setError(t("rulesPage.errorNeedsPattern")); return; }
    setSaving(true);
    setError(null);
    try {
      await api.applyDescriptionRules([{ label: label.trim(), patterns }]);
      onApplied(label.trim());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  const previewCount = 3;
  const isCompact = group.members.length === 1;
  const shown = expanded ? group.members : group.members.slice(0, previewCount);
  const hasMore = group.members.length > previewCount;

  // ── Compact layout: single row ──────────────────────────────────────────
  if (isCompact) {
    const m = group.members[0];
    return (
      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${error ? "border-red-300 dark:border-red-700" : "border-gray-200 dark:border-gray-700"} bg-white dark:bg-gray-900 group`}>
        {/* Count badge */}
        <span className="text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded-full font-medium shrink-0 tabular-nums">
          ×{m.count}
        </span>

        {/* Raw description */}
        <span className="text-xs font-mono text-gray-400 dark:text-gray-500 truncate shrink-0 max-w-[14rem]" title={m.raw}>
          {m.raw}
        </span>

        <span className="text-gray-300 dark:text-gray-600 shrink-0">→</span>

        {/* Label input */}
        <input
          className="w-32 border border-gray-300 dark:border-gray-600 rounded px-2 py-0.5 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-1 ring-indigo-500 shrink-0"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); patternInputRef.current?.focus(); }
            if (e.key === "Escape") onDismissed(group.canonical);
          }}
        />

        {/* Pattern input */}
        <div className="flex-1 min-w-0">
          <PatternInput
            patterns={patterns}
            onChange={setPatterns}
            onEnterEmpty={apply}
            inputRef={patternInputRef}
          />
        </div>

        {/* Apply / dismiss */}
        <button
          onClick={apply}
          disabled={saving}
          className="text-xs px-2.5 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 shrink-0 whitespace-nowrap"
        >
          {saving ? "…" : "↵"}
        </button>
        <button
          onClick={() => onDismissed(group.canonical)}
          className="text-xs text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 shrink-0"
          title={t("rulesPage.dismiss")}
        >
          ✕
        </button>
        {error && <p className="text-xs text-red-500 shrink-0">{error}</p>}
      </div>
    );
  }

  // ── Expanded layout: multiple distinct descriptions ──────────────────────
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-800/50">
        <span className="text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 px-2 py-0.5 rounded-full font-medium shrink-0">
          {group.total_count} {group.total_count === 1 ? t("rulesPage.tx") : t("rulesPage.txPlural")}
        </span>
        <span className="text-sm font-mono text-gray-500 dark:text-gray-400 truncate flex-1">{group.canonical}</span>
      </div>

      {/* Raw descriptions */}
      <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-700">
        <ul className="space-y-0.5">
          {shown.map((m, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-8 text-right shrink-0">×{m.count}</span>
              <span className="text-xs font-mono text-gray-600 dark:text-gray-300 truncate">{m.raw}</span>
            </li>
          ))}
        </ul>
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-indigo-500 hover:underline mt-1"
          >
            {expanded
              ? t("rulesPage.showLess")
              : t("rulesPage.showMore").replace("{n}", String(group.members.length - previewCount))}
          </button>
        )}
      </div>

      {/* Rule editor */}
      <div className="px-4 py-3 flex flex-col gap-2">
        <div className="flex gap-2 items-center">
          <label className="text-xs text-gray-500 w-16 shrink-0">{t("rulesPage.label")}</label>
          <input
            className="flex-1 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-1 ring-indigo-500"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); patternInputRef.current?.focus(); }
              if (e.key === "Escape") onDismissed(group.canonical);
            }}
          />
        </div>
        <div className="flex gap-2 items-start">
          <label className="text-xs text-gray-500 w-16 shrink-0 pt-1.5">{t("rulesPage.patterns")}</label>
          <div className="flex-1">
            <PatternInput
              patterns={patterns}
              onChange={setPatterns}
              onEnterEmpty={apply}
              inputRef={patternInputRef}
            />
            <p className="text-xs text-gray-400 mt-1">{t("rulesPage.patternHint")}</p>
          </div>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => onDismissed(group.canonical)}
            className="text-xs px-3 py-1 rounded border border-gray-200 dark:border-gray-600 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            {t("rulesPage.dismiss")}
          </button>
          <button
            onClick={apply}
            disabled={saving}
            className="text-xs px-3 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? t("rulesPage.applying") : t("rulesPage.createAndApply")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StripTab — per-user prefix/suffix management
// ---------------------------------------------------------------------------

function StripEntryChip({
  entry,
  onDelete,
}: {
  entry: StripConfigEntry;
  onDelete: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-100 text-sm font-mono px-2.5 py-1 rounded-lg">
      {entry.value}
      <button
        type="button"
        onClick={onDelete}
        className="text-gray-400 hover:text-red-500 ml-0.5 leading-none text-base"
        aria-label="Remove"
      >
        ×
      </button>
    </span>
  );
}

function StripAddInput({
  placeholder,
  onAdd,
}: {
  placeholder: string;
  onAdd: (value: string) => void;
}) {
  const [draft, setDraft] = useState("");

  function commit() {
    const val = draft.trim();
    if (val) {
      onAdd(val);
      setDraft("");
    }
  }

  return (
    <div className="flex gap-2 mt-2">
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
        placeholder={placeholder}
        className="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-1 ring-indigo-500"
      />
    </div>
  );
}

function StripTab({
  entries,
  suggestions,
  loadingEntries,
  loadingSuggestions,
  onAdd,
  onDelete,
  onRecategorize,
  recategorizing,
  recategorizeResult,
}: {
  entries: StripConfigEntry[];
  suggestions: StripSuggestion[];
  loadingEntries: boolean;
  loadingSuggestions: boolean;
  onAdd: (type: "prefix" | "suffix", value: string) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onRecategorize: () => void;
  recategorizing: boolean;
  recategorizeResult: string | null;
}) {
  const { t } = useT();

  const prefixes = entries.filter((e) => e.type === "prefix");
  const suffixes = entries.filter((e) => e.type === "suffix");
  const suggestedPrefixes = suggestions.filter((s) => s.type === "prefix");
  const suggestedSuffixes = suggestions.filter((s) => s.type === "suffix");

  return (
    <div className="flex flex-col gap-6">
      {/* Description */}
      <p className="text-sm text-gray-500 dark:text-gray-400">
        {t("rulesPage.stripSubtitle")}
      </p>

      {loadingEntries ? (
        <div className="text-sm text-gray-400 py-4 text-center">{t("rulesPage.loading")}</div>
      ) : (
        <div className="flex flex-col gap-5">
          {/* Prefixes */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              {t("rulesPage.stripPrefixes")}
            </h3>
            {prefixes.length === 0 ? (
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">
                {t("rulesPage.stripNoPrefixes")}
              </p>
            ) : (
              <div className="flex flex-wrap gap-2 mb-2">
                {prefixes.map((e) => (
                  <StripEntryChip
                    key={e.id}
                    entry={e}
                    onDelete={() => onDelete(e.id)}
                  />
                ))}
              </div>
            )}
            <StripAddInput
              placeholder={t("rulesPage.addPrefix")}
              onAdd={(v) => onAdd("prefix", v)}
            />
          </div>

          {/* Suffixes */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              {t("rulesPage.stripSuffixes")}
            </h3>
            {suffixes.length === 0 ? (
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">
                {t("rulesPage.stripNoSuffixes")}
              </p>
            ) : (
              <div className="flex flex-wrap gap-2 mb-2">
                {suffixes.map((e) => (
                  <StripEntryChip
                    key={e.id}
                    entry={e}
                    onDelete={() => onDelete(e.id)}
                  />
                ))}
              </div>
            )}
            <StripAddInput
              placeholder={t("rulesPage.addSuffix")}
              onAdd={(v) => onAdd("suffix", v)}
            />
          </div>

          {/* Apply button */}
          {entries.length > 0 && (
            <div className="flex items-center gap-3">
              <button
                onClick={onRecategorize}
                disabled={recategorizing}
                className="text-sm px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              >
                {recategorizing
                  ? t("rulesPage.stripApplying")
                  : t("rulesPage.stripApply")}
              </button>
              {recategorizeResult && (
                <span className="text-xs text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20 px-3 py-1.5 rounded-lg">
                  {recategorizeResult}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Suggestions */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
          {t("rulesPage.stripSuggestionsTitle")}
        </h3>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">
          {t("rulesPage.stripSuggestionsDesc")}
        </p>

        {loadingSuggestions ? (
          <div className="text-sm text-gray-400 text-center py-4">{t("rulesPage.loading")}</div>
        ) : suggestions.length === 0 ? (
          <p className="text-sm text-gray-400 dark:text-gray-500">
            {t("rulesPage.stripNoSuggestions")}
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {suggestedPrefixes.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                  {t("rulesPage.stripFrequentPrefixes")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {suggestedPrefixes.map((s) => (
                    <div
                      key={s.value}
                      className="inline-flex items-center gap-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-2.5 py-1"
                    >
                      <span className="text-sm font-mono text-amber-800 dark:text-amber-300">
                        {s.value}
                      </span>
                      <span className="text-xs text-amber-600 dark:text-amber-500">
                        ×{s.count}
                      </span>
                      <button
                        type="button"
                        onClick={() => onAdd("prefix", s.value)}
                        className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline whitespace-nowrap"
                      >
                        {t("rulesPage.stripAddAsPrefix")}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {suggestedSuffixes.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                  {t("rulesPage.stripFrequentSuffixes")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {suggestedSuffixes.map((s) => (
                    <div
                      key={s.value}
                      className="inline-flex items-center gap-2 bg-sky-50 dark:bg-sky-900/20 border border-sky-200 dark:border-sky-800 rounded-lg px-2.5 py-1"
                    >
                      <span className="text-sm font-mono text-sky-800 dark:text-sky-300">
                        {s.value}
                      </span>
                      <span className="text-xs text-sky-600 dark:text-sky-500">
                        ×{s.count}
                      </span>
                      <button
                        type="button"
                        onClick={() => onAdd("suffix", s.value)}
                        className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline whitespace-nowrap"
                      >
                        {t("rulesPage.stripAddAsSuffix")}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function RulesPage() {
  const { t } = useT();
  const [rules, setRules] = useState<DescriptionRule[]>([]);
  const [suggestions, setSuggestions] = useState<SuggestionGroup[]>([]);
  const [uncoveredTotal, setUncoveredTotal] = useState(0);
  const [dismissedCanonicals, setDismissedCanonicals] = useState<Set<string>>(new Set());
  const [loadingRules, setLoadingRules] = useState(true);
  const [loadingSuggestions, setLoadingSuggestions] = useState(true);
  const [tab, setTab] = useState<"rules" | "suggestions" | "strip">("suggestions");
  const [search, setSearch] = useState("");
  const [recategorizing, setRecategorizing] = useState(false);
  const [recategorizeResult, setRecategorizeResult] = useState<string | null>(null);

  // Strip config state
  const [stripEntries, setStripEntries] = useState<StripConfigEntry[]>([]);
  const [stripSuggestions, setStripSuggestions] = useState<StripSuggestion[]>([]);
  const [loadingStripEntries, setLoadingStripEntries] = useState(true);
  const [loadingStripSuggestions, setLoadingStripSuggestions] = useState(true);
  const [stripRecategorizing, setStripRecategorizing] = useState(false);
  const [stripRecategorizeResult, setStripRecategorizeResult] = useState<string | null>(null);

  const loadRules = useCallback(async () => {
    setLoadingRules(true);
    try {
      const data: RuleListResponse = await api.descriptionRules();
      setRules(data.rules);
    } finally {
      setLoadingRules(false);
    }
  }, []);

  const loadSuggestions = useCallback(async () => {
    setLoadingSuggestions(true);
    try {
      const data: SuggestionsResponse = await api.descriptionSuggestions(100);
      setSuggestions(data.groups);
      setUncoveredTotal(data.uncovered_total);
    } finally {
      setLoadingSuggestions(false);
    }
  }, []);

  const loadStripEntries = useCallback(async () => {
    setLoadingStripEntries(true);
    try {
      const data = await api.stripConfig();
      setStripEntries(data.entries);
    } finally {
      setLoadingStripEntries(false);
    }
  }, []);

  const loadStripSuggestions = useCallback(async () => {
    setLoadingStripSuggestions(true);
    try {
      const data = await api.stripSuggestions();
      setStripSuggestions(data.suggestions);
    } finally {
      setLoadingStripSuggestions(false);
    }
  }, []);

  useEffect(() => {
    loadRules();
    loadSuggestions();
    loadStripEntries();
    loadStripSuggestions();
  }, [loadRules, loadSuggestions, loadStripEntries, loadStripSuggestions]);

  // --- Rules panel handlers ---
  function handleRuleSaved(updated: DescriptionRule) {
    setRules((prev) =>
      prev.map((r) => (r.label === updated.label || r.label === updated.label ? updated : r))
    );
  }

  function handleRuleDeleted(label: string) {
    setRules((prev) => prev.filter((r) => r.label !== label));
  }

  function handleRuleAdded(rule: DescriptionRule) {
    setRules((prev) => [...prev, rule]);
  }

  // --- Suggestions panel handlers ---
  function handleSuggestionApplied(label: string) {
    // reload both panels after apply
    loadRules();
    loadSuggestions();
    setRecategorizeResult(t("rulesPage.appliedSuccess").replace("{label}", label));
    setTimeout(() => setRecategorizeResult(null), 4000);
  }

  function handleDismissed(canonical: string) {
    setDismissedCanonicals((prev) => new Set([...prev, canonical]));
  }

  // --- Strip config handlers ---
  async function handleStripAdd(type: "prefix" | "suffix", value: string) {
    try {
      const entry = await api.addStripEntry(type, value);
      setStripEntries((prev) => [...prev, entry]);
      // Refresh suggestions (newly added entry is excluded from them)
      loadStripSuggestions();
    } catch (e: unknown) {
      console.error(e);
    }
  }

  async function handleStripDelete(id: number) {
    try {
      await api.deleteStripEntry(id);
      setStripEntries((prev) => prev.filter((e) => e.id !== id));
      loadStripSuggestions();
    } catch (e: unknown) {
      console.error(e);
    }
  }

  async function handleStripRecategorize() {
    setStripRecategorizing(true);
    setStripRecategorizeResult(null);
    try {
      const res = await api.recategorize(false);
      setStripRecategorizeResult(
        t("rulesPage.stripAppliedSuccess").replace("{n}", String(res.updated))
      );
      loadRules(); // refresh match counts
      loadSuggestions(); // suggestions now based on stripped_description
    } catch (e: unknown) {
      setStripRecategorizeResult(e instanceof Error ? e.message : String(e));
    } finally {
      setStripRecategorizing(false);
      setTimeout(() => setStripRecategorizeResult(null), 5000);
    }
  }

  async function recategorizeAll() {
    setRecategorizing(true);
    setRecategorizeResult(null);
    try {
      const res = await api.recategorize(false);
      setRecategorizeResult(
        t("rulesPage.recategorizeSuccess").replace("{n}", String(res.updated))
      );
      loadRules(); // refresh match counts
    } catch (e: unknown) {
      setRecategorizeResult(e instanceof Error ? e.message : String(e));
    } finally {
      setRecategorizing(false);
      setTimeout(() => setRecategorizeResult(null), 5000);
    }
  }

  const filteredRules = rules
    .filter(
      (r) =>
        r.label.toLowerCase().includes(search.toLowerCase()) ||
        r.patterns.some((p) => p.toLowerCase().includes(search.toLowerCase()))
    )
    .sort((a, b) => b.match_count - a.match_count);

  const visibleSuggestions = suggestions.filter(
    (g) => !dismissedCanonicals.has(g.canonical)
  );

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-950 pb-16">
      {/* Page header */}
      <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
              {t("rulesPage.title")}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              {t("rulesPage.subtitle")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {recategorizeResult && (
              <span className="text-xs text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20 px-3 py-1.5 rounded-lg">
                {recategorizeResult}
              </span>
            )}
            <button
              onClick={recategorizeAll}
              disabled={recategorizing}
              className="text-sm px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {recategorizing ? t("rulesPage.applyingAll") : t("rulesPage.recategorizeAll")}
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 flex flex-col gap-6 lg:flex-row lg:items-start">

        {/* ── Left panel: existing rules ───────────────────────────────── */}
        <div className="flex-1 min-w-0">
          {/* Tab bar */}
          <div className="flex gap-1 mb-4 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setTab("rules")}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === "rules"
                  ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400"
              }`}
            >
              {t("rulesPage.tabRules")}
              <span className="ml-1.5 text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded-full">
                {rules.length}
              </span>
            </button>
            <button
              onClick={() => setTab("suggestions")}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === "suggestions"
                  ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400"
              }`}
            >
              {t("rulesPage.tabSuggestions")}
              {visibleSuggestions.length > 0 && (
                <span className="ml-1.5 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded-full">
                  {visibleSuggestions.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setTab("strip")}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === "strip"
                  ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400"
              }`}
            >
              {t("rulesPage.tabStrip")}
              {stripEntries.length > 0 && (
                <span className="ml-1.5 text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded-full">
                  {stripEntries.length}
                </span>
              )}
            </button>
          </div>

          {/* Rules tab */}
          {tab === "rules" && (
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              {/* Search */}
              <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-800">
                <input
                  className="w-full text-sm bg-transparent outline-none text-gray-700 dark:text-gray-200 placeholder-gray-400"
                  placeholder={t("rulesPage.search")}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>

              {loadingRules ? (
                <div className="px-4 py-8 text-center text-sm text-gray-400">{t("rulesPage.loading")}</div>
              ) : filteredRules.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-gray-400">
                  {search ? t("rulesPage.noMatch") : t("rulesPage.noRules")}
                </div>
              ) : (
                <div>
                  {/* Header row */}
                  <div className="flex items-center gap-3 px-4 py-1.5 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800 text-xs text-gray-400">
                    <span className="w-8 text-right shrink-0">#</span>
                    <span className="w-44 shrink-0">{t("rulesPage.colLabel")}</span>
                    <span className="flex-1">{t("rulesPage.colPatterns")}</span>
                  </div>
                  {filteredRules.map((rule) => (
                    <RuleRow
                      key={rule.label}
                      rule={rule}
                      onSaved={handleRuleSaved}
                      onDeleted={handleRuleDeleted}
                    />
                  ))}
                </div>
              )}
              <NewRuleForm onSaved={handleRuleAdded} />
            </div>
          )}

          {/* Suggestions tab */}
          {tab === "suggestions" && (
            <div>
              {loadingSuggestions ? (
                <div className="py-8 text-center text-sm text-gray-400">{t("rulesPage.loading")}</div>
              ) : visibleSuggestions.length === 0 ? (
                <div className="py-12 text-center">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {uncoveredTotal === 0
                      ? t("rulesPage.allCovered")
                      : t("rulesPage.noPendingSuggestions")}
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-4">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t("rulesPage.suggestionIntro")
                      .replace("{groups}", String(visibleSuggestions.length))
                      .replace("{total}", String(uncoveredTotal))}
                  </p>
                  {visibleSuggestions.map((group) => (
                    <SuggestionCard
                      key={group.canonical}
                      group={group}
                      onApplied={handleSuggestionApplied}
                      onDismissed={handleDismissed}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
          {/* Strip tab */}
          {tab === "strip" && (
            <StripTab
              entries={stripEntries}
              suggestions={stripSuggestions}
              loadingEntries={loadingStripEntries}
              loadingSuggestions={loadingStripSuggestions}
              onAdd={handleStripAdd}
              onDelete={handleStripDelete}
              onRecategorize={handleStripRecategorize}
              recategorizing={stripRecategorizing}
              recategorizeResult={stripRecategorizeResult}
            />
          )}
        </div>
      </div>
    </main>
  );
}
