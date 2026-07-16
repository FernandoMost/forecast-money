"use client";

import { useEffect, useState, useCallback } from "react";
import { api, CategoryWithChildren, CategoryItem, CategoryRole } from "@/lib/api";
import { useT } from "@/lib/i18n";

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

function ColorPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (c: string) => void;
}) {
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

// ─── Category dot ─────────────────────────────────────────────────────────────

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

// ─── Form helpers ─────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
      {children}
    </div>
  );
}

const inputCls = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-white";

// ─── Create category modal ────────────────────────────────────────────────────

interface CreateModalProps {
  parentId?: string | null;
  parentName?: string;
  onClose: () => void;
  onCreated: () => void;
}

function CreateModal({ parentId, parentName, onClose, onCreated }: CreateModalProps) {
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
          <input
            className={inputCls}
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder={t("categories.fieldIdPlaceholder")}
          />
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
          <select
            className={inputCls}
            value={role}
            onChange={(e) => setRole(e.target.value as CategoryRole | "")}
          >
            {roleOptions.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </Field>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
            {t("categories.cancel")}
          </button>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? t("categories.creating") : t("categories.create")}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ─── Edit modal ────────────────────────────────────────────────────────────────

interface EditModalProps {
  cat: CategoryWithChildren | CategoryItem;
  isTopLevel: boolean;
  onClose: () => void;
  onSaved: () => void;
}

function EditModal({ cat, isTopLevel, onClose, onSaved }: EditModalProps) {
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
          <select
            className={inputCls}
            value={role}
            onChange={(e) => setRole(e.target.value as CategoryRole | "")}
          >
            {roleOptions.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
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

// ─── Delete confirm modal ─────────────────────────────────────────────────────

interface DeleteModalProps {
  cat: CategoryWithChildren | CategoryItem;
  onClose: () => void;
  onDeleted: () => void;
}

function DeleteModal({ cat, onClose, onDeleted }: DeleteModalProps) {
  const { t } = useT();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const hasChildren = "subcategories" in cat && cat.subcategories.length > 0;

  async function handleDelete() {
    setLoading(true);
    setError("");
    try {
      const res = await api.deleteCategory(cat.id);
      if (res.affected_transactions > 0) {
        // inform but proceed — transactions now have null category
      }
      onDeleted();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("categories.errorDelete"));
      setLoading(false);
    }
  }

  return (
    <Modal title={t("categories.deleteTitle", { name: cat.name })} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t("categories.deleteBody", { name: cat.name })}
        </p>
        {hasChildren && (
          <p className="text-sm text-amber-700 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 rounded-lg px-3 py-2">
            {t("categories.deleteSubWarning", { count: (cat as CategoryWithChildren).subcategories.length })}
          </p>
        )}
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">{t("categories.cancel")}</button>
          <button
            onClick={handleDelete}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
          >
            {loading ? t("categories.deleting") : t("categories.delete")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

type ModalState =
  | { type: "create-top" }
  | { type: "create-sub"; parentId: string; parentName: string }
  | { type: "edit-top"; cat: CategoryWithChildren }
  | { type: "edit-sub"; cat: CategoryItem }
  | { type: "delete-top"; cat: CategoryWithChildren }
  | { type: "delete-sub"; cat: CategoryItem }
  | null;

export default function CategoriesPage() {
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
      // Auto-expand all top-level categories
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
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("categories.title")}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            {t("categories.subtitle")}
          </p>
        </div>
        <button
          onClick={() => setModal({ type: "create-top" })}
          className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
        >
          {t("categories.newCategory")}
        </button>
      </div>

      {/* Role legend */}
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="text-gray-500 dark:text-gray-400 self-center">{t("categories.rolesLabel")}</span>
        {roleOptions.filter((r) => r.value !== "").map((r) => (
          <span key={r.value} className={`px-2 py-0.5 rounded-full ${r.color}`}>{r.label}</span>
        ))}
      </div>

      {/* State */}
      {loading && <p className="text-sm text-gray-400 dark:text-gray-500">{t("categories.loading")}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Category list */}
      {!loading && !error && (
        <div className="space-y-3">
          {categories.map((cat) => {
            const expanded = expandedIds.has(cat.id);
            return (
              <div key={cat.id} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
                {/* Top-level row */}
                <div className="flex items-center gap-3 px-4 py-3">
                  {/* Expand toggle */}
                  <button
                    type="button"
                    onClick={() => toggleExpand(cat.id)}
                    className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 w-5 text-center flex-shrink-0 transition-transform"
                    style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}
                    aria-label={expanded ? t("categories.collapse") : t("categories.expand")}
                  >
                    ▶
                  </button>
                  {/* Color dot */}
                  <Dot color={cat.color} />
                  {/* Color preview swatch (small) */}
                  <span className="font-medium text-gray-900 dark:text-white flex-1 min-w-0">
                    {cat.name}
                    <span className="ml-2 text-xs text-gray-400 dark:text-gray-500 font-normal">{cat.id}</span>
                  </span>
                  <RoleBadge role={cat.role} />
                  <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums w-16 text-right">
                    {t("categories.subCount", { count: cat.subcategories.length })}
                  </span>
                  {/* Actions */}
                  <div className="flex gap-1 ml-2">
                    <button
                      onClick={() => setModal({ type: "create-sub", parentId: cat.id, parentName: cat.name })}
                      className="px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded"
                      title="Add subcategory"
                    >
                      {t("categories.addSub")}
                    </button>
                    <button
                      onClick={() => setModal({ type: "edit-top", cat })}
                      className="px-2 py-1 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
                    >
                      {t("categories.edit")}
                    </button>
                    <button
                      onClick={() => setModal({ type: "delete-top", cat })}
                      className="px-2 py-1 text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 rounded"
                    >
                      {t("categories.delete")}
                    </button>
                  </div>
                </div>

                {/* Subcategories */}
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
                          <button
                            onClick={() => setModal({ type: "edit-sub", cat: sub })}
                            className="px-2 py-0.5 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                          >
                            {t("categories.edit")}
                          </button>
                          <button
                            onClick={() => setModal({ type: "delete-sub", cat: sub })}
                            className="px-2 py-0.5 text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 rounded"
                          >
                            {t("categories.delete")}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Empty state for subcategories */}
                {expanded && cat.subcategories.length === 0 && (
                  <div className="px-12 py-2 text-xs text-gray-400 dark:text-gray-500 border-t border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-800/40">
                    {t("categories.noSubs")}{" "}
                    <button
                      onClick={() => setModal({ type: "create-sub", parentId: cat.id, parentName: cat.name })}
                      className="text-indigo-500 hover:underline"
                    >
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

      {/* Modals */}
      {modal?.type === "create-top" && (
        <CreateModal onClose={closeModal} onCreated={refresh} />
      )}
      {modal?.type === "create-sub" && (
        <CreateModal
          parentId={modal.parentId}
          parentName={modal.parentName}
          onClose={closeModal}
          onCreated={refresh}
        />
      )}
      {modal?.type === "edit-top" && (
        <EditModal cat={modal.cat} isTopLevel onClose={closeModal} onSaved={refresh} />
      )}
      {modal?.type === "edit-sub" && (
        <EditModal cat={modal.cat} isTopLevel={false} onClose={closeModal} onSaved={refresh} />
      )}
      {modal?.type === "delete-top" && (
        <DeleteModal cat={modal.cat} onClose={closeModal} onDeleted={refresh} />
      )}
      {modal?.type === "delete-sub" && (
        <DeleteModal cat={modal.cat} onClose={closeModal} onDeleted={refresh} />
      )}
    </div>
  );
}
