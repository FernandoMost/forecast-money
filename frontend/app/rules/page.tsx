"use client";

import { useEffect, useState, useCallback } from "react";
import {
  api,
  DescriptionRule,
  SuggestionGroup,
  SuggestionsResponse,
  RuleListResponse,
} from "@/lib/api";
import { useT } from "@/lib/i18n";

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
}: {
  patterns: string[];
  onChange: (p: string[]) => void;
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
        className="flex-1 min-w-[6rem] bg-transparent outline-none text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400"
        placeholder={t("rules.patternPlaceholder")}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
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
      setError(t("rules.errorNeedsPattern"));
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
    if (!confirm(t("rules.confirmDelete").replace("{label}", rule.label))) return;
    try {
      await api.deleteDescriptionRule(rule.label);
      onDeleted(rule.label);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  if (!editing) {
    return (
      <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-800/50 group border-b border-gray-100 dark:border-gray-800 last:border-0">
        <StatusBadge n={rule.match_count} />
        <span className="font-medium text-sm text-gray-800 dark:text-gray-100 w-44 shrink-0 truncate">
          {rule.label}
        </span>
        <div className="flex flex-wrap gap-1 flex-1 min-w-0">
          {rule.patterns.map((p, i) => (
            <PatternTag key={i} value={p} />
          ))}
        </div>
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            onClick={() => setEditing(true)}
            className="text-xs px-2 py-1 rounded text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            {t("rules.edit")}
          </button>
          <button
            onClick={remove}
            className="text-xs px-2 py-1 rounded text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
          >
            {t("rules.delete")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 bg-indigo-50/30 dark:bg-indigo-900/10">
      <div className="flex flex-col gap-2">
        <div className="flex gap-2 items-center">
          <label className="text-xs text-gray-500 w-16 shrink-0">{t("rules.label")}</label>
          <input
            className="flex-1 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <div className="flex gap-2 items-start">
          <label className="text-xs text-gray-500 w-16 shrink-0 pt-1.5">{t("rules.patterns")}</label>
          <div className="flex-1">
            <PatternInput patterns={patterns} onChange={setPatterns} />
            <p className="text-xs text-gray-400 mt-1">{t("rules.patternHint")}</p>
          </div>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button
            onClick={cancel}
            className="text-xs px-3 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            {t("rules.cancel")}
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="text-xs px-3 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? t("rules.saving") : t("rules.save")}
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
    if (!label.trim()) { setError(t("rules.errorNeedsLabel")); return; }
    if (!patterns.length) { setError(t("rules.errorNeedsPattern")); return; }
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
        + {t("rules.addRule")}
      </button>
    );
  }

  return (
    <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800 bg-indigo-50/30 dark:bg-indigo-900/10">
      <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">{t("rules.addRule")}</p>
      <div className="flex flex-col gap-2">
        <div className="flex gap-2 items-center">
          <label className="text-xs text-gray-500 w-16 shrink-0">{t("rules.label")}</label>
          <input
            className="flex-1 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            placeholder={t("rules.labelPlaceholder")}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") save(); }}
          />
        </div>
        <div className="flex gap-2 items-start">
          <label className="text-xs text-gray-500 w-16 shrink-0 pt-1.5">{t("rules.patterns")}</label>
          <div className="flex-1">
            <PatternInput patterns={patterns} onChange={setPatterns} />
            <p className="text-xs text-gray-400 mt-1">{t("rules.patternHint")}</p>
          </div>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => { setOpen(false); setError(null); }}
            className="text-xs px-3 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            {t("rules.cancel")}
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="text-xs px-3 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? t("rules.saving") : t("rules.save")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SuggestionCard — one suggestion group
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

  async function apply() {
    if (!label.trim()) { setError(t("rules.errorNeedsLabel")); return; }
    if (!patterns.length) { setError(t("rules.errorNeedsPattern")); return; }
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
  const shown = expanded ? group.members : group.members.slice(0, previewCount);
  const hasMore = group.members.length > previewCount;

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-800/50">
        <span className="text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 px-2 py-0.5 rounded-full font-medium shrink-0">
          {group.total_count} {group.total_count === 1 ? t("rules.tx") : t("rules.txPlural")}
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
              ? t("rules.showLess")
              : t("rules.showMore").replace("{n}", String(group.members.length - previewCount))}
          </button>
        )}
      </div>

      {/* Rule editor */}
      <div className="px-4 py-3 flex flex-col gap-2">
        <div className="flex gap-2 items-center">
          <label className="text-xs text-gray-500 w-16 shrink-0">{t("rules.label")}</label>
          <input
            className="flex-1 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <div className="flex gap-2 items-start">
          <label className="text-xs text-gray-500 w-16 shrink-0 pt-1.5">{t("rules.patterns")}</label>
          <div className="flex-1">
            <PatternInput patterns={patterns} onChange={setPatterns} />
            <p className="text-xs text-gray-400 mt-1">{t("rules.patternHint")}</p>
          </div>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => onDismissed(group.canonical)}
            className="text-xs px-3 py-1 rounded border border-gray-200 dark:border-gray-600 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            {t("rules.dismiss")}
          </button>
          <button
            onClick={apply}
            disabled={saving}
            className="text-xs px-3 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? t("rules.applying") : t("rules.createAndApply")}
          </button>
        </div>
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
  const [tab, setTab] = useState<"rules" | "suggestions">("suggestions");
  const [search, setSearch] = useState("");
  const [recategorizing, setRecategorizing] = useState(false);
  const [recategorizeResult, setRecategorizeResult] = useState<string | null>(null);

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

  useEffect(() => {
    loadRules();
    loadSuggestions();
  }, [loadRules, loadSuggestions]);

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
    setRecategorizeResult(t("rules.appliedSuccess").replace("{label}", label));
    setTimeout(() => setRecategorizeResult(null), 4000);
  }

  function handleDismissed(canonical: string) {
    setDismissedCanonicals((prev) => new Set([...prev, canonical]));
  }

  async function recategorizeAll() {
    setRecategorizing(true);
    setRecategorizeResult(null);
    try {
      const res = await api.recategorize(false);
      setRecategorizeResult(
        t("rules.recategorizeSuccess").replace("{n}", String(res.updated))
      );
      loadRules(); // refresh match counts
    } catch (e: unknown) {
      setRecategorizeResult(e instanceof Error ? e.message : String(e));
    } finally {
      setRecategorizing(false);
      setTimeout(() => setRecategorizeResult(null), 5000);
    }
  }

  const filteredRules = rules.filter(
    (r) =>
      r.label.toLowerCase().includes(search.toLowerCase()) ||
      r.patterns.some((p) => p.toLowerCase().includes(search.toLowerCase()))
  );

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
              {t("rules.title")}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              {t("rules.subtitle")}
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
              {recategorizing ? t("rules.applyingAll") : t("rules.recategorizeAll")}
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
              {t("rules.tabRules")}
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
              {t("rules.tabSuggestions")}
              {visibleSuggestions.length > 0 && (
                <span className="ml-1.5 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded-full">
                  {visibleSuggestions.length}
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
                  placeholder={t("rules.search")}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>

              {loadingRules ? (
                <div className="px-4 py-8 text-center text-sm text-gray-400">{t("rules.loading")}</div>
              ) : filteredRules.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-gray-400">
                  {search ? t("rules.noMatch") : t("rules.noRules")}
                </div>
              ) : (
                <div>
                  {/* Header row */}
                  <div className="flex items-center gap-3 px-4 py-1.5 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800 text-xs text-gray-400">
                    <span className="w-8 text-right shrink-0">#</span>
                    <span className="w-44 shrink-0">{t("rules.colLabel")}</span>
                    <span className="flex-1">{t("rules.colPatterns")}</span>
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
                <div className="py-8 text-center text-sm text-gray-400">{t("rules.loading")}</div>
              ) : visibleSuggestions.length === 0 ? (
                <div className="py-12 text-center">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {uncoveredTotal === 0
                      ? t("rules.allCovered")
                      : t("rules.noPendingSuggestions")}
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-4">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t("rules.suggestionIntro")
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
        </div>
      </div>
    </main>
  );
}
