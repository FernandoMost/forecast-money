"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  api,
  CategoryWithChildren,
  CategoryItem,
  CategoryRole,
  CategoryRuleItem,
  CategorySuggestionGroup,
  ReviewKeyword,
  ReviewTransactionItem,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { formatEur, formatDate, formatDateSlash } from "@/lib/utils";
import { useCategoryTree, invalidateCategoryCache } from "@/components/CategoryTree";

// ─── Role metadata ──────────────────────────────────────────────────────────

const ROLE_OPTION_DEFS: { value: CategoryRole | ""; color: string; key: string }[] = [
  { value: "",              color: "bg-gray-100 text-gray-600",    key: "categories.roles.none" },
  { value: "income",        color: "bg-green-100 text-green-700",  key: "categories.roles.income" },
  { value: "needs",         color: "bg-blue-100 text-blue-700",    key: "categories.roles.needs" },
  { value: "wants",         color: "bg-purple-100 text-purple-700",key: "categories.roles.wants" },
  { value: "leisure",       color: "bg-orange-100 text-orange-700",key: "categories.roles.leisure" },
  { value: "fixed",         color: "bg-indigo-100 text-indigo-700",key: "categories.roles.fixed" },
  { value: "subscriptions", color: "bg-violet-100 text-violet-700",key: "categories.roles.subscriptions" },
  { value: "savings",       color: "bg-teal-100 text-teal-700",    key: "categories.roles.savings" },
  { value: "other",         color: "bg-gray-100 text-gray-500",    key: "categories.roles.other" },
];

function getRoleOptions(t: (key: string) => string) {
  return ROLE_OPTION_DEFS.map((r) => ({ ...r, label: t(r.key) }));
}

function RoleBadge({ role }: { role: string | null }) {
  const { t } = useT();
  const roleOptions = getRoleOptions(t);
  const opt = roleOptions.find((r) => r.value === (role ?? ""));
  if (!role) return null;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${opt?.color ?? "bg-gray-100 text-gray-500"}`}>
      {opt?.label ?? role}
    </span>
  );
}

// ─── Color swatch ─────────────────────────────────────────────────────────────

const PRESET_COLORS = [
  "#6366f1", "#a855f7", "#ec4899", "#f97316", "#eab308",
  "#22c55e", "#14b8a6", "#0ea5e9", "#84cc16", "#94a3b8",
  "#78716c", "#64748b", "#d1d5db",
];

function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  const { t } = useT();
  return (
    <div className="flex flex-wrap gap-2 items-center">
      {PRESET_COLORS.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onChange(c)}
          className={`w-6 h-6 rounded-full border-2 transition-transform hover:scale-110 ${
            value === c ? "border-gray-900 scale-110" : "border-transparent"
          }`}
          style={{ backgroundColor: c }}
          title={c}
        />
      ))}
      <input
        type="color"
        value={value || "#6366f1"}
        onChange={(e) => onChange(e.target.value)}
        className="w-6 h-6 rounded cursor-pointer border border-gray-300"
        title={t("categories.fieldColorTitle")}
      />
    </div>
  );
}

function Dot({ color }: { color: string | null }) {
  return (
    <span
      className="inline-block w-3 h-3 rounded-full flex-shrink-0"
      style={{ backgroundColor: color ?? "#d1d5db" }}
    />
  );
}

// ─── Modal shell ─────────────────────────────────────────────────────────────

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xl leading-none">&times;</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
      {children}
    </div>
  );
}

const inputCls = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-white";

// ─── Category modals ──────────────────────────────────────────────────────────

function CreateModal({
  parentId,
  parentName,
  onClose,
  onCreated,
}: {
  parentId?: string | null;
  parentName?: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useT();
  const roleOptions = getRoleOptions(t);
  const isSubcat = !!parentId;
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [color, setColor] = useState("#6366f1");
  const [role, setRole] = useState<CategoryRole | "">("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!id.trim() || !name.trim()) { setError(t("categories.validationIdName")); return; }
    if (!/^[a-z0-9_]+$/.test(id)) { setError(t("categories.validationIdFormat")); return; }
    setLoading(true);
    setError("");
    try {
      await api.createCategory({
        id: id.trim(),
        name: name.trim(),
        parent_id: parentId ?? null,
        color: isSubcat ? null : color,
        role: (role || null) as CategoryRole | null,
        position: 99,
      });
      invalidateCategoryCache();
      onCreated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("categories.errorCreate"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal title={isSubcat ? t("categories.createSubTitle", { parent: parentName ?? "" }) : t("categories.createTitle")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label={t("categories.fieldId")}>
          <input className={inputCls} value={id} onChange={(e) => setId(e.target.value)} placeholder={t("categories.fieldIdPlaceholder")} />
          <p className="text-xs text-gray-400 dark:text-gray-500">{t("categories.fieldIdHint")}</p>
        </Field>
        <Field label={t("categories.fieldName")}>
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("categories.fieldNamePlaceholder")} />
        </Field>
        {!isSubcat && (
          <Field label={t("categories.fieldColor")}>
            <ColorPicker value={color} onChange={setColor} />
          </Field>
        )}
        <Field label={t("categories.fieldRole")}>
          <select className={inputCls} value={role} onChange={(e) => setRole(e.target.value as CategoryRole | "")}>
            {roleOptions.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </Field>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">{t("categories.cancel")}</button>
          <button type="submit" disabled={loading} className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
            {loading ? t("categories.creating") : t("categories.create")}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function EditModal({
  cat,
  isTopLevel,
  onClose,
  onSaved,
}: {
  cat: CategoryWithChildren | CategoryItem;
  isTopLevel: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useT();
  const roleOptions = getRoleOptions(t);
  const [name, setName] = useState(cat.name);
  const [color, setColor] = useState(cat.color ?? "#6366f1");
  const [role, setRole] = useState<CategoryRole | "">(cat.role ?? "");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { setError(t("categories.validationName")); return; }
    setLoading(true);
    setError("");
    try {
      await api.updateCategory(cat.id, {
        name: name.trim(),
        color: isTopLevel ? color : null,
        role: (role || null) as CategoryRole | null,
      });
      invalidateCategoryCache();
      onSaved();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("categories.errorUpdate"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal title={t("categories.editTitle", { name: cat.name })} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label={t("categories.fieldName")}>
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        {isTopLevel && (
          <Field label={t("categories.fieldColor")}>
            <ColorPicker value={color} onChange={setColor} />
          </Field>
        )}
        <Field label={t("categories.fieldRole")}>
          <select className={inputCls} value={role} onChange={(e) => setRole(e.target.value as CategoryRole | "")}>
            {roleOptions.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </Field>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">{t("categories.cancel")}</button>
          <button type="submit" disabled={loading} className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
            {loading ? t("categories.saving") : t("categories.save")}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteModal({
  cat,
  onClose,
  onDeleted,
}: {
  cat: CategoryWithChildren | CategoryItem;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { t } = useT();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const hasChildren = "subcategories" in cat && cat.subcategories.length > 0;

  async function handleDelete() {
    setLoading(true);
    setError("");
    try {
      await api.deleteCategory(cat.id);
      invalidateCategoryCache();
      onDeleted();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("categories.errorDelete"));
      setLoading(false);
    }
  }

  return (
    <Modal title={t("categories.deleteTitle", { name: cat.name })} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-gray-600 dark:text-gray-400">{t("categories.deleteBody", { name: cat.name })}</p>
        {hasChildren && (
          <p className="text-sm text-amber-700 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 rounded-lg px-3 py-2">
            {t("categories.deleteSubWarning", { count: (cat as CategoryWithChildren).subcategories.length })}
          </p>
        )}
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">{t("categories.cancel")}</button>
          <button onClick={handleDelete} disabled={loading} className="px-4 py-2 text-sm font-medium bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50">
            {loading ? t("categories.deleting") : t("categories.delete")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Category Rules Tab ───────────────────────────────────────────────────────

interface CategoryRuleFormState {
  category: string;
  subcategory: string;
  patterns: string[];
  patternInput: string;
}

function CategoryRulesTab() {
  const { t } = useT();
  const { categories, catLabel, subLabel } = useCategoryTree();
  const [rules, setRules] = useState<CategoryRuleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [applyMsg, setApplyMsg] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<CategoryRuleFormState>({ category: "", subcategory: "", patterns: [], patternInput: "" });
  const [showNewForm, setShowNewForm] = useState(false);
  const [newForm, setNewForm] = useState<CategoryRuleFormState>({ category: "", subcategory: "", patterns: [], patternInput: "" });
  const [error, setError] = useState("");

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.categoryRules();
      setRules(res.rules);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadRules(); }, [loadRules]);

  async function handleApplyAll() {
    setApplying(true);
    setApplyMsg("");
    try {
      const res = await api.applyCategoryRules();
      setApplyMsg(t("categoryRules.appliedSuccess", { n: res.updated }));
    } catch { /* ignore */ }
    setApplying(false);
  }

  async function handleDelete(id: number) {
    if (!window.confirm(t("categoryRules.confirmDelete"))) return;
    await api.deleteCategoryRule(id);
    loadRules();
  }

  function startEdit(rule: CategoryRuleItem) {
    setEditId(rule.id);
    setEditForm({ category: rule.category, subcategory: rule.subcategory ?? "", patterns: rule.patterns, patternInput: "" });
  }

  async function saveEdit() {
    if (!editId) return;
    setError("");
    if (!editForm.category) { setError(t("categoryRules.errorNeedsCategory")); return; }
    if (!editForm.patterns.length) { setError(t("categoryRules.errorNeedsPattern")); return; }
    try {
      await api.updateCategoryRule(editId, {
        category: editForm.category,
        subcategory: editForm.subcategory || null,
        patterns: editForm.patterns,
      });
      setEditId(null);
      loadRules();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error");
    }
  }

  async function saveNew() {
    setError("");
    if (!newForm.category) { setError(t("categoryRules.errorNeedsCategory")); return; }
    if (!newForm.patterns.length) { setError(t("categoryRules.errorNeedsPattern")); return; }
    try {
      await api.createCategoryRule({
        category: newForm.category,
        subcategory: newForm.subcategory || null,
        patterns: newForm.patterns,
      });
      setShowNewForm(false);
      setNewForm({ category: "", subcategory: "", patterns: [], patternInput: "" });
      loadRules();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error");
    }
  }

  function addPattern(form: CategoryRuleFormState, setForm: React.Dispatch<React.SetStateAction<CategoryRuleFormState>>, value: string) {
    const v = value.trim();
    if (v && !form.patterns.includes(v)) {
      setForm((f) => ({ ...f, patterns: [...f.patterns, v], patternInput: "" }));
    } else {
      setForm((f) => ({ ...f, patternInput: "" }));
    }
  }

  function removePattern(form: CategoryRuleFormState, setForm: React.Dispatch<React.SetStateAction<CategoryRuleFormState>>, p: string) {
    setForm((f) => ({ ...f, patterns: f.patterns.filter((x) => x !== p) }));
  }

  const topLevel = categories;
  const getSubcats = (catId: string) => categories.find((c) => c.id === catId)?.subcategories ?? [];

  function CategoryRuleForm({
    form,
    setForm,
    onSave,
    onCancel,
    saving,
  }: {
    form: CategoryRuleFormState;
    setForm: React.Dispatch<React.SetStateAction<CategoryRuleFormState>>;
    onSave: () => void;
    onCancel: () => void;
    saving?: boolean;
  }) {
    return (
      <div className="space-y-3 p-4 bg-indigo-50 dark:bg-indigo-950/20 rounded-lg border border-indigo-200 dark:border-indigo-800">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{t("categoryRules.fieldCategory")}</label>
            <select
              className={inputCls}
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value, subcategory: "" }))}
            >
              <option value="">—</option>
              {topLevel.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{t("categoryRules.fieldSubcategory")}</label>
            <select
              className={inputCls}
              value={form.subcategory}
              onChange={(e) => setForm((f) => ({ ...f, subcategory: e.target.value }))}
              disabled={!form.category}
            >
              <option value="">—</option>
              {getSubcats(form.category).map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{t("categoryRules.fieldPatterns")}</label>
          <div className="flex flex-wrap gap-1 mb-1">
            {form.patterns.map((p) => (
              <span key={p} className="flex items-center gap-1 text-xs bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 rounded px-2 py-0.5 font-mono">
                {p}
                <button type="button" onClick={() => removePattern(form, setForm, p)} className="text-indigo-400 hover:text-red-500 ml-0.5">×</button>
              </span>
            ))}
          </div>
          <input
            className={inputCls}
            value={form.patternInput}
            onChange={(e) => setForm((f) => ({ ...f, patternInput: e.target.value }))}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addPattern(form, setForm, form.patternInput); }
            }}
            placeholder={t("categoryRules.patternPlaceholder")}
          />
        </div>
        {error && <p className="text-red-600 text-xs">{error}</p>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onCancel} className="px-3 py-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
            {t("categoryRules.cancel")}
          </button>
          <button type="button" onClick={onSave} disabled={saving} className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50">
            {saving ? t("categoryRules.saving") : t("categoryRules.save")}
          </button>
        </div>
      </div>
    );
  }

  if (loading) return <p className="text-sm text-gray-400 py-8">{t("categories.loading")}</p>;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{t("categoryRules.rulesSubtitle")}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleApplyAll}
            disabled={applying}
            className="px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            {applying ? t("categoryRules.applying") : t("categoryRules.applyAndRecategorize")}
          </button>
          <button
            onClick={() => setShowNewForm(true)}
            className="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            {t("categoryRules.newRule")}
          </button>
        </div>
      </div>
      {applyMsg && <p className="text-sm text-green-600 dark:text-green-400">{applyMsg}</p>}

      {/* New rule form */}
      {showNewForm && (
        <CategoryRuleForm
          form={newForm}
          setForm={setNewForm}
          onSave={saveNew}
          onCancel={() => { setShowNewForm(false); setError(""); }}
        />
      )}

      {/* Rules list */}
      {rules.length === 0 && !showNewForm && (
        <p className="text-sm text-gray-400 py-8 text-center">{t("categoryRules.noRules")}</p>
      )}

      <div className="space-y-2">
        {rules.map((rule, idx) => (
          <div key={rule.id}>
            {editId === rule.id ? (
              <CategoryRuleForm
                form={editForm}
                setForm={setEditForm}
                onSave={saveEdit}
                onCancel={() => { setEditId(null); setError(""); }}
              />
            ) : (
              <div className="flex items-center gap-3 p-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-indigo-200 dark:hover:border-indigo-800 group">
                <span className="text-xs text-gray-400 tabular-nums w-6 text-center flex-shrink-0">{idx + 1}</span>
                {/* Category */}
                <div className="flex items-center gap-1 min-w-0 w-36 flex-shrink-0">
                  <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                    {catLabel(rule.category)}
                  </span>
                  {rule.subcategory && (
                    <span className="text-xs text-gray-400 dark:text-gray-500 truncate">/ {subLabel(rule.subcategory)}</span>
                  )}
                </div>
                {/* Patterns */}
                <div className="flex flex-wrap gap-1 flex-1 min-w-0">
                  {rule.patterns.map((p) => (
                    <span key={p} className="text-xs font-mono bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded px-1.5 py-0.5">{p}</span>
                  ))}
                </div>
                {/* Match count */}
                <span className="text-xs text-gray-400 tabular-nums w-12 text-right flex-shrink-0">{rule.match_count}</span>
                {/* Actions */}
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={() => startEdit(rule)} className="px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
                    {t("categoryRules.edit")}
                  </button>
                  <button onClick={() => handleDelete(rule.id)} className="px-2 py-0.5 text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 rounded">
                    {t("categoryRules.delete")}
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Category Suggestions Tab ─────────────────────────────────────────────────

function CategorySuggestionsTab() {
  const { t, locale } = useT();
  const { categories, catLabel, subLabel } = useCategoryTree();
  const [groups, setGroups] = useState<CategorySuggestionGroup[]>([]);
  const [uncoveredTotal, setUncoveredTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [selection, setSelection] = useState<Record<string, { category: string; subcategory: string; createRule: boolean }>>({});

  const loadSuggestions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.categorySuggestions();
      setGroups(res.groups);
      setUncoveredTotal(res.uncovered_total);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadSuggestions(); }, [loadSuggestions]);

  const topLevel = categories;
  const getSubcats = (catId: string) => categories.find((c) => c.id === catId)?.subcategories ?? [];

  function getSelection(cd: string) {
    return selection[cd] ?? { category: "", subcategory: "", createRule: false };
  }

  function updateSelection(cd: string, patch: Partial<{ category: string; subcategory: string; createRule: boolean }>) {
    setSelection((prev) => ({
      ...prev,
      [cd]: { ...getSelection(cd), ...patch },
    }));
  }

  async function handleApply(cd: string) {
    const sel = getSelection(cd);
    if (!sel.category) return;
    setApplying(cd);
    try {
      await api.applyCategorySuggestion({
        clean_description: cd,
        category: sel.category,
        subcategory: sel.subcategory || null,
        create_rule: sel.createRule,
      });
      setGroups((prev) => prev.filter((g) => g.clean_description !== cd));
      setUncoveredTotal((n) => Math.max(0, n - 1));
    } catch { /* ignore */ }
    setApplying(null);
  }

  async function handleDismiss(cd: string) {
    await api.dismissCategorySuggestion(cd);
    setGroups((prev) => prev.filter((g) => g.clean_description !== cd));
    setUncoveredTotal((n) => Math.max(0, n - 1));
  }

  if (loading) return <p className="text-sm text-gray-400 py-8">{t("categories.loading")}</p>;

  if (groups.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400 dark:text-gray-500">
        <p className="text-sm">{t("categoryRules.suggestionsEmpty")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        {t("categoryRules.suggestionsSubtitle", { count: uncoveredTotal })}
      </p>
      <div className="space-y-3">
        {groups.map((g) => {
          const sel = getSelection(g.clean_description);
          const isApplying = applying === g.clean_description;
          const subcats = getSubcats(sel.category);
          const dateStr = g.latest_date ? formatDate(g.latest_date, locale === "es" ? "es-ES" : "en-GB") : "";
          return (
            <div key={g.clean_description} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-900 dark:text-white text-sm truncate">{g.clean_description}</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                    {t("categoryRules.suggestionsCount", { n: g.count, date: dateStr })}
                  </p>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <select
                  className={inputCls + " text-xs py-1.5"}
                  value={sel.category}
                  onChange={(e) => updateSelection(g.clean_description, { category: e.target.value, subcategory: "" })}
                >
                  <option value="">— {t("categoryRules.fieldCategory")} —</option>
                  {topLevel.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
                <select
                  className={inputCls + " text-xs py-1.5"}
                  value={sel.subcategory}
                  onChange={(e) => updateSelection(g.clean_description, { subcategory: e.target.value })}
                  disabled={!sel.category || subcats.length === 0}
                >
                  <option value="">— {t("categoryRules.fieldSubcategory")} —</option>
                  {subcats.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              <div className="mt-2 flex items-center gap-3">
                <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={sel.createRule}
                    onChange={(e) => updateSelection(g.clean_description, { createRule: e.target.checked })}
                    className="rounded text-indigo-600"
                  />
                  {t("categoryRules.createRule")}
                </label>
                <div className="flex-1" />
                <button
                  onClick={() => handleDismiss(g.clean_description)}
                  className="text-xs text-gray-400 hover:text-red-500 px-2 py-1"
                >
                  {t("categoryRules.dismiss")}
                </button>
                <button
                  onClick={() => handleApply(g.clean_description)}
                  disabled={!sel.category || isApplying}
                  className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  {isApplying ? t("categoryRules.applying2") : t("categoryRules.apply")}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Categories Tab ────────────────────────────────────────────────────────────

type ModalState =
  | { type: "create-top" }
  | { type: "create-sub"; parentId: string; parentName: string }
  | { type: "edit-top"; cat: CategoryWithChildren }
  | { type: "edit-sub"; cat: CategoryItem }
  | { type: "delete-top"; cat: CategoryWithChildren }
  | { type: "delete-sub"; cat: CategoryItem }
  | null;

function CategoriesTab() {
  const { t } = useT();
  const roleOptions = getRoleOptions(t);
  const [categories, setCategories] = useState<CategoryWithChildren[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modal, setModal] = useState<ModalState>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.categories();
      setCategories(res.categories);
      setExpandedIds(new Set(res.categories.map((c) => c.id)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load categories.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function closeModal() { setModal(null); }
  function refresh() { setModal(null); load(); }

  return (
    <div className="space-y-4">
      {/* Header row with + button */}
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="text-gray-500 dark:text-gray-400 self-center">{t("categories.rolesLabel")}</span>
          {roleOptions.filter((r) => r.value !== "").map((r) => (
            <span key={r.value} className={`px-2 py-0.5 rounded-full ${r.color}`}>{r.label}</span>
          ))}
        </div>
        <button
          onClick={() => setModal({ type: "create-top" })}
          className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
        >
          {t("categories.newCategory")}
        </button>
      </div>

      {loading && <p className="text-sm text-gray-400 dark:text-gray-500">{t("categories.loading")}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {!loading && !error && (
        <div className="space-y-3">
          {categories.map((cat) => {
            const expanded = expandedIds.has(cat.id);
            return (
              <div key={cat.id} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
                <div className="flex items-center gap-3 px-4 py-3">
                  <button
                    type="button"
                    onClick={() => toggleExpand(cat.id)}
                    className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 w-5 text-center flex-shrink-0 transition-transform"
                    style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}
                    aria-label={expanded ? t("categories.collapse") : t("categories.expand")}
                  >▶</button>
                  <Dot color={cat.color} />
                  <span className="font-medium text-gray-900 dark:text-white flex-1 min-w-0">
                    {cat.name}
                    <span className="ml-2 text-xs text-gray-400 dark:text-gray-500 font-normal">{cat.id}</span>
                  </span>
                  <RoleBadge role={cat.role} />
                  <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums w-16 text-right">
                    {t("categories.subCount", { count: cat.subcategories.length })}
                  </span>
                  <div className="flex gap-1 ml-2">
                    <button onClick={() => setModal({ type: "create-sub", parentId: cat.id, parentName: cat.name })} className="px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded">
                      {t("categories.addSub")}
                    </button>
                    <button onClick={() => setModal({ type: "edit-top", cat })} className="px-2 py-1 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
                      {t("categories.edit")}
                    </button>
                    <button onClick={() => setModal({ type: "delete-top", cat })} className="px-2 py-1 text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 rounded">
                      {t("categories.delete")}
                    </button>
                  </div>
                </div>
                {expanded && cat.subcategories.length > 0 && (
                  <div className="border-t border-gray-100 dark:border-gray-800 divide-y divide-gray-50 dark:divide-gray-800">
                    {cat.subcategories.map((sub) => (
                      <div key={sub.id} className="flex items-center gap-3 px-4 py-2 pl-12 bg-gray-50/60 dark:bg-gray-800/40 hover:bg-gray-50 dark:hover:bg-gray-800">
                        <span className="text-gray-700 dark:text-gray-300 flex-1 text-sm">
                          {sub.name}
                          <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">{sub.id}</span>
                        </span>
                        <RoleBadge role={sub.role} />
                        <div className="flex gap-1">
                          <button onClick={() => setModal({ type: "edit-sub", cat: sub })} className="px-2 py-0.5 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded">
                            {t("categories.edit")}
                          </button>
                          <button onClick={() => setModal({ type: "delete-sub", cat: sub })} className="px-2 py-0.5 text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 rounded">
                            {t("categories.delete")}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {expanded && cat.subcategories.length === 0 && (
                  <div className="px-12 py-2 text-xs text-gray-400 dark:text-gray-500 border-t border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-800/40">
                    {t("categories.noSubs")}{" "}
                    <button onClick={() => setModal({ type: "create-sub", parentId: cat.id, parentName: cat.name })} className="text-indigo-500 hover:underline">
                      {t("categories.addOne")}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
          {categories.length === 0 && (
            <div className="text-center py-16 text-gray-400 dark:text-gray-500">
              {t("categories.noCategories")}{" "}
              <button onClick={() => setModal({ type: "create-top" })} className="text-indigo-500 hover:underline">
                {t("categories.createFirst")}
              </button>
            </div>
          )}
        </div>
      )}

      {modal?.type === "create-top" && <CreateModal onClose={closeModal} onCreated={refresh} />}
      {modal?.type === "create-sub" && <CreateModal parentId={modal.parentId} parentName={modal.parentName} onClose={closeModal} onCreated={refresh} />}
      {modal?.type === "edit-top" && <EditModal cat={modal.cat} isTopLevel onClose={closeModal} onSaved={refresh} />}
      {modal?.type === "edit-sub" && <EditModal cat={modal.cat} isTopLevel={false} onClose={closeModal} onSaved={refresh} />}
      {modal?.type === "delete-top" && <DeleteModal cat={modal.cat} onClose={closeModal} onDeleted={refresh} />}
      {modal?.type === "delete-sub" && <DeleteModal cat={modal.cat} onClose={closeModal} onDeleted={refresh} />}
    </div>
  );
}

// ─── Review Tab — opaque marketplace purchases (Vinted / Amazon / PayPal…) ───

const REVIEW_PAGE = 50;

function ReviewTab({ onCountRefresh }: { onCountRefresh: () => void }) {
  const { t, locale } = useT();
  const { categories, catLabel, subLabel } = useCategoryTree();
  const intlLocale = locale === "es" ? "es-ES" : "en-GB";
  const [items, setItems] = useState<ReviewTransactionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [keywords, setKeywords] = useState<ReviewKeyword[]>([]);
  const [loadingKeywords, setLoadingKeywords] = useState(true);
  const [newKeyword, setNewKeyword] = useState("");
  const [keywordError, setKeywordError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Record<string, { category: string; subcategory: string }>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});

  const load = useCallback(async (offset = 0, append = false) => {
    if (offset === 0) setLoading(true); else setLoadingMore(true);
    try {
      const data = await api.reviewTransactions(REVIEW_PAGE, offset);
      setTotal(data.total);
      setItems((prev) => (append ? [...prev, ...data.items] : data.items));
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  const loadKeywords = useCallback(async () => {
    try {
      setKeywords(await api.reviewKeywords());
    } catch { /* ignore */ }
    setLoadingKeywords(false);
  }, []);

  useEffect(() => { loadKeywords(); }, [loadKeywords]);
  useEffect(() => { load(0); }, [load]);

  // Adding/removing a keyword widens or narrows the queue → reload it
  const keywordsReady = useRef(false);
  useEffect(() => {
    if (!keywordsReady.current) { keywordsReady.current = true; return; }
    load(0);
  }, [keywords, load]);

  function getSel(id: string) {
    return selection[id] ?? { category: "", subcategory: "" };
  }

  function updateSel(id: string, patch: Partial<{ category: string; subcategory: string }>) {
    setSelection((prev) => ({ ...prev, [id]: { ...getSel(id), ...patch } }));
  }

  function removeFromList(id: string) {
    setItems((prev) => prev.filter((i) => i.id !== id));
    setTotal((n) => Math.max(0, n - 1));
    onCountRefresh();  // badge reloads from the API (not optimistic)
  }

  async function applyReview(
    tx: ReviewTransactionItem,
    category: string,
    subcategory: string,
  ) {
    setSaving((s) => ({ ...s, [tx.id]: true }));
    try {
      // PATCH marks category_source='manual' → leaves the queue and survives recategorizations
      await api.patchTransaction(tx.id, {
        category,
        subcategory: subcategory || null,
      });
      removeFromList(tx.id);
    } catch { /* keep the row on error */ }
    finally {
      setSaving((s) => {
        const copy = { ...s };
        delete copy[tx.id];
        return copy;
      });
    }
  }

  async function addKeyword() {
    const kw = newKeyword.trim();
    if (!kw || loadingKeywords) return;
    setKeywordError(null);
    try {
      await api.addReviewKeyword(kw);
      setNewKeyword("");
      await loadKeywords();
    } catch {
      setKeywordError(t("reviewTab.errorAddKeyword"));
    }
  }

  async function deleteKeyword(id: number) {
    await api.deleteReviewKeyword(id).catch(() => {});
    await loadKeywords();
  }

  if (loading) {
    return <p className="text-sm text-gray-400 py-8 text-center">{t("categories.loading")}</p>;
  }

  return (
    <div className="space-y-4">
      {/* Keywords */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-2">
          {t("reviewTab.keywordsTitle")}
        </h3>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {keywords.map((k) => (
            <span
              key={k.id}
              className="inline-flex items-center gap-1 text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 rounded-full pl-2.5 pr-1 py-1"
            >
              {k.keyword}
              <button
                onClick={() => deleteKeyword(k.id)}
                title={t("reviewTab.removeKeyword")}
                className="rounded-full text-gray-400 hover:text-red-500 px-1"
              >
                ×
              </button>
            </span>
          ))}
          {keywords.length === 0 && !loadingKeywords && (
            <span className="text-xs text-gray-400">{t("reviewTab.noKeywords")}</span>
          )}
        </div>
        <div className="flex gap-2">
          <input
            value={newKeyword}
            onChange={(e) => setNewKeyword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addKeyword(); } }}
            placeholder={t("reviewTab.keywordPlaceholder")}
            className={inputCls + " text-xs py-1.5 flex-1"}
          />
          <button
            onClick={addKeyword}
            disabled={!newKeyword.trim()}
            className="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 shrink-0"
          >
            {t("reviewTab.addKeyword")}
          </button>
        </div>
        {keywordError && <p className="text-xs text-red-600 dark:text-red-400 mt-1.5">{keywordError}</p>}
      </div>

      {/* Queue */}
      <p className="text-xs text-gray-400 dark:text-gray-500 px-1">{t("reviewTab.hint")}</p>

      {items.length === 0 ? (
        <div className="text-center py-16 text-gray-400 dark:text-gray-500">
          <p className="text-2xl mb-2">✓</p>
          <p className="text-sm">{t("reviewTab.empty")}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((tx) => {
            const sel = getSel(tx.id);
            const isSaving = saving[tx.id] ?? false;
            const subcats = categories.find((c) => c.id === sel.category)?.subcategories ?? [];
            const current = tx.category
              ? tx.subcategory
                ? `${catLabel(tx.category)} / ${subLabel(tx.subcategory)}`
                : catLabel(tx.category)
              : t("reviewTab.noneCategory");
            return (
              <div
                key={tx.id}
                className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-3 shadow-sm"
              >
                <div className="flex items-center gap-3 text-sm">
                  <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0 w-24 tabular-nums">
                    {formatDateSlash(tx.date, intlLocale)}
                  </span>
                  <span className="flex-1 min-w-0 truncate" title={tx.raw_description}>
                    {tx.description}
                  </span>
                  {tx.proration_months && (
                    <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-300 text-[10px] font-semibold">
                      ÷{tx.proration_months.length}
                    </span>
                  )}
                  <span className={`shrink-0 text-xs font-mono font-medium tabular-nums w-20 text-right ${tx.amount < 0 ? "text-red-600 dark:text-red-400" : "text-green-600"}`}>
                    {formatEur(tx.amount)}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-2 pl-1">
                  <span className="text-[11px] text-gray-400 dark:text-gray-500 shrink-0">
                    {t("reviewTab.current")}:
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 font-medium">
                      {current}
                    </span>
                  </span>
                  <div className="flex-1" />
                  {tx.category && (
                    <button
                      onClick={() => applyReview(tx, tx.category!, tx.subcategory ?? "")}
                      disabled={isSaving}
                      title={t("reviewTab.keepTitle")}
                      className="text-xs px-2 py-1 rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-green-50 dark:hover:bg-green-900/20 hover:border-green-300 disabled:opacity-40 shrink-0"
                    >
                      {isSaving ? "…" : t("reviewTab.keep")}
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <select
                    className={inputCls + " text-xs py-1.5"}
                    value={sel.category}
                    onChange={(e) => updateSel(tx.id, { category: e.target.value, subcategory: "" })}
                    disabled={isSaving}
                  >
                    <option value="">— {t("reviewTab.pickCategory")} —</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                  <select
                    className={inputCls + " text-xs py-1.5"}
                    value={sel.subcategory}
                    onChange={(e) => updateSel(tx.id, { subcategory: e.target.value })}
                    disabled={isSaving || !sel.category || subcats.length === 0}
                  >
                    <option value="">— {t("reviewTab.pickSubcategory")} —</option>
                    {subcats.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                <div className="flex justify-end mt-2">
                  <button
                    onClick={() => applyReview(tx, sel.category, sel.subcategory)}
                    disabled={isSaving || !sel.category}
                    className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40"
                  >
                    {isSaving ? "…" : t("reviewTab.assign")}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Load more */}
      {items.length < total && (
        <button
          onClick={() => load(items.length, true)}
          disabled={loadingMore}
          className="w-full py-2.5 text-sm text-indigo-600 dark:text-indigo-400 hover:underline disabled:opacity-50"
        >
          {loadingMore ? "…" : t("reviewTab.loadMore")}
          <span className="ml-1 text-xs text-gray-400">({total - items.length})</span>
        </button>
      )}
    </div>
  );
}

type Tab = "categories" | "rules" | "suggestions" | "review";

export default function CategoriesPage() {
  const { t } = useT();
  const [tab, setTab] = useState<Tab>("categories");
  const [suggestionCount, setSuggestionCount] = useState<number | null>(null);
  const [reviewCount, setReviewCount] = useState<number | null>(null);

  // Load suggestion badge count on mount
  useEffect(() => {
    api.categorySuggestions(1).then((res) => setSuggestionCount(res.uncovered_total)).catch(() => {});
    api.reviewTransactions(1).then((res) => setReviewCount(res.total)).catch(() => {});
  }, []);

  // Badge reloads from the API (not optimistic) after each review action
  function refreshReviewCount() {
    api.reviewTransactions(1).then((res) => setReviewCount(res.total)).catch(() => {});
  }

  const tabs: { key: Tab; label: string; badge?: number | null }[] = [
    { key: "categories", label: t("categoryRules.tabCategories") },
    { key: "rules",      label: t("categoryRules.tabRules") },
    { key: "suggestions", label: t("categoryRules.tabSuggestions"), badge: suggestionCount },
    { key: "review",     label: t("categoryRules.tabReview"), badge: reviewCount },
  ];

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("categories.title")}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{t("categories.subtitle")}</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {tabs.map((tb) => (
          <button
            key={tb.key}
            onClick={() => setTab(tb.key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === tb.key
                ? "border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400"
                : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
          >
            {tb.label}
            {tb.badge != null && tb.badge > 0 && (
              <span className="text-xs bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 rounded-full px-1.5 py-0.5 font-semibold leading-none">
                {tb.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "categories" && <CategoriesTab />}
      {tab === "rules" && <CategoryRulesTab />}
      {tab === "suggestions" && <CategorySuggestionsTab />}
      {tab === "review" && <ReviewTab onCountRefresh={refreshReviewCount} />}
    </div>
  );
}
