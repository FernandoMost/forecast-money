"use client";

// CategoryTree.tsx
// Reusable category + subcategory selector used in:
//   - /transactions filter bar
//   - inline transaction edit form
//
// The taxonomy is loaded from GET /api/v1/categories and cached in a
// module-level variable so a single fetch serves the whole session.
//
// Exported helpers:
//   catLabel(id)           — human-readable category name
//   subLabel(id)           — human-readable subcategory name
//   CATEGORY_TREE          — Record<parentId, subcategoryId[]> (built from API data)
//   useCategoryTree()      — hook that returns { tree, catLabel, subLabel, loading }
//
// Usage (filter mode — shows "All" option):
//   <CategoryTree
//     selected={{ category: "groceries", subcategory: null }}
//     onChange={(cat, sub) => setFilter(cat, sub)}
//     showAll
//   />
//
// Usage (edit mode — no "All", must pick a leaf):
//   <CategoryTree
//     selected={{ category: tx.category, subcategory: tx.subcategory }}
//     onChange={(cat, sub) => setEdit(cat, sub)}
//   />

import { useEffect, useState } from "react";
import { api, CategoryWithChildren } from "@/lib/api";

export interface CategorySelection {
  category: string | null;
  subcategory: string | null;
}

// ───────────────────────────────────────────────────────────────────────────
// Module-level cache — fetched once per browser session
// ───────────────────────────────────────────────────────────────────────────

let _cachedCategories: CategoryWithChildren[] | null = null;
let _fetchPromise: Promise<CategoryWithChildren[]> | null = null;

function fetchCategories(): Promise<CategoryWithChildren[]> {
  if (_cachedCategories) return Promise.resolve(_cachedCategories);
  if (_fetchPromise) return _fetchPromise;
  _fetchPromise = api.categories().then((res) => {
    _cachedCategories = res.categories;
    _fetchPromise = null;
    return _cachedCategories;
  });
  return _fetchPromise;
}

// Invalidate cache (called after categories are created/edited/deleted)
export function invalidateCategoryCache() {
  _cachedCategories = null;
  _fetchPromise = null;
}

// ───────────────────────────────────────────────────────────────────────────
// Derived helpers built from API data
// ───────────────────────────────────────────────────────────────────────────

function buildHelpers(cats: CategoryWithChildren[]) {
  const tree: Record<string, string[]> = {};
  const catLabels: Record<string, string> = {};
  const subLabels: Record<string, string> = {};
  const colorMap: Record<string, string> = {};

  for (const c of cats) {
    tree[c.id] = c.subcategories.map((s) => s.id);
    catLabels[c.id] = c.name;
    if (c.color) colorMap[c.id] = c.color;
    for (const s of c.subcategories) {
      subLabels[s.id] = s.name;
    }
  }
  return { tree, catLabels, subLabels, colorMap };
}

// ───────────────────────────────────────────────────────────────────────────
// Static fallback — used before the first API response arrives
// Mirrors config/category_rules.yaml so the UI is immediately usable
// ───────────────────────────────────────────────────────────────────────────

const _FALLBACK_TREE: Record<string, string[]> = {
  income:        ["payroll", "transfer_in", "bizum_in", "refund", "paypal_in"],
  housing:       ["rent", "utilities_electricity", "utilities_water", "utilities_heating", "internet_phone"],
  subscriptions: ["streaming", "gym", "sports_club", "paypal_sub", "pagatelia", "other_sub"],
  groceries:     ["supermarket", "other_food_shop"],
  restaurants:   ["fast_food", "restaurant", "cafe_bakery", "bar_pub"],
  transport:     ["parking", "fuel", "rideshare", "public_transit", "train_station", "tyre_service"],
  health:        ["pharmacy", "medical"],
  shopping:      ["online", "clothing", "electronics", "general"],
  entertainment: ["cinema", "events", "gaming"],
  transfers:     ["rent_contribution", "bizum_out", "transfer_out"],
  cash:          ["atm_withdrawal"],
  admin:         ["city_tax", "travel_tickets"],
  uncategorized: ["other"],
};

const _FALLBACK_CAT_LABELS: Record<string, string> = {
  income: "Income", housing: "Housing", subscriptions: "Subscriptions",
  groceries: "Groceries", restaurants: "Restaurants", transport: "Transport",
  health: "Health", shopping: "Shopping", entertainment: "Entertainment",
  transfers: "Transfers", cash: "Cash", admin: "Admin", uncategorized: "Uncategorized",
};

const _FALLBACK_SUB_LABELS: Record<string, string> = {
  payroll: "Payroll", transfer_in: "Transfer in", bizum_in: "Bizum in",
  refund: "Refund", paypal_in: "PayPal in",
  rent: "Rent", utilities_electricity: "Electricity", utilities_water: "Water",
  utilities_heating: "Heating", internet_phone: "Internet / Phone",
  streaming: "Streaming", gym: "Gym", sports_club: "Sports club",
  paypal_sub: "PayPal sub", pagatelia: "Pagatelia", other_sub: "Other sub",
  supermarket: "Supermarket", other_food_shop: "Other food shop",
  fast_food: "Fast food", restaurant: "Restaurant", cafe_bakery: "Café / Bakery", bar_pub: "Bar / Pub",
  parking: "Parking", fuel: "Fuel", rideshare: "Rideshare",
  public_transit: "Public transit", train_station: "Train", tyre_service: "Tyres",
  pharmacy: "Pharmacy", medical: "Medical",
  online: "Online", clothing: "Clothing", electronics: "Electronics", general: "General",
  cinema: "Cinema", events: "Events", gaming: "Gaming",
  rent_contribution: "Rent contribution", bizum_out: "Bizum out", transfer_out: "Transfer out",
  atm_withdrawal: "ATM withdrawal",
  city_tax: "City tax", travel_tickets: "Travel tickets",
  other: "Other",
};

const _FALLBACK_COLORS: Record<string, string> = {
  housing: "#6366f1", groceries: "#22c55e", restaurants: "#f97316",
  transport: "#0ea5e9", subscriptions: "#a855f7", shopping: "#ec4899",
  entertainment: "#eab308", health: "#14b8a6", income: "#84cc16",
  transfers: "#94a3b8", cash: "#78716c", admin: "#64748b", uncategorized: "#d1d5db",
};

// ───────────────────────────────────────────────────────────────────────────
// Module-level state that mirrors the latest fetched data
// (allows non-hook callers like `catLabel()` to work after first load)
// ───────────────────────────────────────────────────────────────────────────

let _activeCatLabels: Record<string, string> = _FALLBACK_CAT_LABELS;
let _activeSubLabels: Record<string, string> = _FALLBACK_SUB_LABELS;
let _activeTree: Record<string, string[]> = _FALLBACK_TREE;
let _activeColors: Record<string, string> = _FALLBACK_COLORS;

// ───────────────────────────────────────────────────────────────────────────
// Exported static-like helpers (work with fallback until API loads)
// ───────────────────────────────────────────────────────────────────────────

/** Human-readable label for a top-level category id */
export function catLabel(id: string): string {
  return _activeCatLabels[id] ?? id;
}

/** Human-readable label for a subcategory id */
export function subLabel(id: string): string {
  return _activeSubLabels[id] ?? id;
}

/** Color hex for a top-level category id */
export function categoryColor(id: string): string {
  return _activeColors[id] ?? "#d1d5db";
}

/** Live tree: Record<categoryId, subcategoryId[]> */
export let CATEGORY_TREE: Record<string, string[]> = _FALLBACK_TREE;

/** Ordered list of top-level category ids */
export let CATEGORY_LIST: string[] = Object.keys(_FALLBACK_TREE);

// ───────────────────────────────────────────────────────────────────────────
// Hook
// ───────────────────────────────────────────────────────────────────────────

interface CategoryTreeState {
  categories: CategoryWithChildren[];
  tree: Record<string, string[]>;
  catLabel: (id: string) => string;
  subLabel: (id: string) => string;
  categoryColor: (id: string) => string;
  loading: boolean;
}

export function useCategoryTree(): CategoryTreeState {
  const [categories, setCategories] = useState<CategoryWithChildren[]>(_cachedCategories ?? []);
  const [loading, setLoading] = useState(!_cachedCategories);
  const [helpers, setHelpers] = useState(() => ({
    tree: _activeTree,
    catLabels: _activeCatLabels,
    subLabels: _activeSubLabels,
    colorMap: _activeColors,
  }));

  useEffect(() => {
    fetchCategories().then((cats) => {
      const { tree, catLabels, subLabels, colorMap } = buildHelpers(cats);
      // Update module-level state so non-hook callers also get fresh data
      _activeCatLabels = catLabels;
      _activeSubLabels = subLabels;
      _activeTree = tree;
      _activeColors = colorMap;
      CATEGORY_TREE = tree;
      CATEGORY_LIST = cats.map((c) => c.id);
      setCategories(cats);
      setHelpers({ tree, catLabels, subLabels, colorMap });
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return {
    categories,
    tree: helpers.tree,
    catLabel: (id: string) => helpers.catLabels[id] ?? id,
    subLabel: (id: string) => helpers.subLabels[id] ?? id,
    categoryColor: (id: string) => helpers.colorMap[id] ?? "#d1d5db",
    loading,
  };
}

// ───────────────────────────────────────────────────────────────────────────
// Component
// ───────────────────────────────────────────────────────────────────────────

interface Props {
  selected: CategorySelection;
  onChange: (category: string | null, subcategory: string | null) => void;
  /** Show an "All categories" option at the start (filter mode) */
  showAll?: boolean;
}

export default function CategoryTree({ selected, onChange, showAll = false }: Props) {
  const { tree, catLabel: label, subLabel: slabel, loading } = useCategoryTree();
  const { category: selCat, subcategory: selSub } = selected;
  const categoryList = Object.keys(tree);
  const subcategories = selCat ? tree[selCat] ?? [] : [];

  function selectCategory(cat: string | null) {
    if (showAll && cat === selCat) {
      onChange(null, null);
    } else {
      onChange(cat, null);
    }
  }

  function selectSubcategory(sub: string) {
    if (sub === selSub) {
      onChange(selCat, null);
    } else {
      onChange(selCat, sub);
    }
  }

  if (loading && categoryList.length === 0) {
    return <div className="text-xs text-gray-400">Loading categories…</div>;
  }

  return (
    <div className="space-y-1.5">
      {/* Category row */}
      <div className="flex flex-wrap gap-1.5">
        {showAll && (
          <button
            type="button"
            onClick={() => onChange(null, null)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              !selCat
                ? "bg-gray-800 text-white border-gray-800"
                : "bg-white text-gray-600 border-gray-300 hover:border-gray-500"
            }`}
          >
            All
          </button>
        )}
        {categoryList.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => selectCategory(cat)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              selCat === cat
                ? "bg-indigo-600 text-white border-indigo-600"
                : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400"
            }`}
          >
            {label(cat)}
          </button>
        ))}
      </div>

      {/* Subcategory row — only visible when a category is selected */}
      {selCat && subcategories.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-2 border-l-2 border-indigo-200">
          {showAll && (
            <button
              type="button"
              onClick={() => onChange(selCat, null)}
              className={`px-2.5 py-0.5 rounded-full text-xs border transition-colors ${
                !selSub
                  ? "bg-indigo-100 text-indigo-700 border-indigo-300 font-medium"
                  : "bg-white text-gray-500 border-gray-200 hover:border-indigo-300"
              }`}
            >
              All {label(selCat)}
            </button>
          )}
          {subcategories.map((sub) => (
            <button
              key={sub}
              type="button"
              onClick={() => selectSubcategory(sub)}
              className={`px-2.5 py-0.5 rounded-full text-xs border transition-colors ${
                selSub === sub
                  ? "bg-indigo-500 text-white border-indigo-500 font-medium"
                  : "bg-white text-gray-500 border-gray-200 hover:border-indigo-300"
              }`}
            >
              {slabel(sub)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
