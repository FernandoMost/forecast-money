"use client";

// CategoryTree.tsx
// Reusable category + subcategory selector used in:
//   - /transactions filter bar
//   - inline transaction edit form
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

export interface CategorySelection {
  category: string | null;
  subcategory: string | null;
}

// -----------------------------------------------------------------------
// Taxonomy — mirrors config/category_rules.yaml
// -----------------------------------------------------------------------

export const CATEGORY_TREE: Record<string, string[]> = {
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

export const CATEGORY_LIST = Object.keys(CATEGORY_TREE);

// Human-readable labels
const CAT_LABEL: Record<string, string> = {
  income: "Income", housing: "Housing", subscriptions: "Subscriptions",
  groceries: "Groceries", restaurants: "Restaurants", transport: "Transport",
  health: "Health", shopping: "Shopping", entertainment: "Entertainment",
  transfers: "Transfers", cash: "Cash", admin: "Admin", uncategorized: "Uncategorized",
};

const SUB_LABEL: Record<string, string> = {
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

export function catLabel(c: string) { return CAT_LABEL[c] ?? c; }
export function subLabel(s: string) { return SUB_LABEL[s] ?? s; }

// -----------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------

interface Props {
  selected: CategorySelection;
  onChange: (category: string | null, subcategory: string | null) => void;
  /** Show an "All categories" option at the start (filter mode) */
  showAll?: boolean;
}

export default function CategoryTree({ selected, onChange, showAll = false }: Props) {
  const { category: selCat, subcategory: selSub } = selected;
  const subcategories = selCat ? CATEGORY_TREE[selCat] ?? [] : [];

  function selectCategory(cat: string | null) {
    // Clicking the already-selected category collapses it (filter mode only)
    if (showAll && cat === selCat) {
      onChange(null, null);
    } else {
      onChange(cat, null);
    }
  }

  function selectSubcategory(sub: string) {
    // Clicking the already-selected subcategory deselects it
    if (sub === selSub) {
      onChange(selCat, null);
    } else {
      onChange(selCat, sub);
    }
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
        {CATEGORY_LIST.map((cat) => (
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
            {catLabel(cat)}
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
              All {catLabel(selCat)}
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
              {subLabel(sub)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
