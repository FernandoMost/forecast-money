# Frontend — agent notes

## Stack
- Next.js 14, TypeScript, Tailwind CSS
- TanStack Table v8 (`@tanstack/react-table`) — transactions table
- Server Components by default; pages with state/effects must be `"use client"`
- API base: `http://localhost:8000/api/v1` (env: `NEXT_PUBLIC_API_URL`)

## Routes
| Path | File | Type | Notes |
|---|---|---|---|
| `/` | `app/page.tsx` | Client Component | Dashboard |
| `/transactions` | `app/transactions/page.tsx` | Client Component | TanStack Table, sort/filter/paginate |
| `/trends` | `app/trends/page.tsx` | Client Component | Trends view |
| `/upload` | `app/upload/page.tsx` | Client Component | Statement upload |
| `/health` | `app/health/page.tsx` | Client Component | Financial health score + rules |
| `/categories` | `app/categories/page.tsx` | Client Component | Category CRUD |
| `/rules` | `app/rules/page.tsx` | Client Component | Description rules CRUD + suggestion engine |
| `/login` | `app/login/page.tsx` | Client Component | Auth |

## Key files
| File | Role |
|---|---|
| `lib/api.ts` | Typed API client — all fetch calls go here |
| `lib/utils.ts` | `formatEur()`, `formatPercent()`, `formatDate()`, `formatMonth()`, `toIntlLocale()`, `STATUS_COLORS` |
| `lib/i18n.tsx` | i18n context — `useT()` returns `{ t, locale, setLocale }` |
| `lib/theme.tsx` | Dark mode — `useTheme()` returns `{ isDark, toggleTheme }` |
| `lib/translateRule.ts` | Translates health rule IDs + details into localised strings |
| `components/Nav.tsx` | Top navigation bar |
| `components/CategoryTree.tsx` | Reusable category+subcategory pill selector; also exports `CATEGORY_TREE`, `catLabel()`, `subLabel()` |
| `components/Providers.tsx` | Wraps app with i18n + theme providers |
| `messages/es.json` | Spanish strings — sections: nav, dashboard, transactions, health, categories, rules (financial), rulesPage (UI) |
| `messages/en.json` | English strings — same sections |

## `lib/api.ts` — key types and calls
```typescript
api.dashboard()              // GET /dashboard → DashboardData
api.transactions(params)     // GET /transactions → TransactionList
api.patchTransaction(id, {   // PATCH /transactions/{id}
  clean_description, category, subcategory   // all optional — omit to preserve
})
api.months()                 // GET /months → { months: string[] }
api.summary(month)           // GET /summary/{month} → MonthlySummary
api.upload(file, bank, useAi)
api.recategorize(useAi)
// Description rules:
api.descriptionRules()                                    // GET /description-rules
api.createDescriptionRule(label, patterns, position?)     // POST
api.updateDescriptionRule(label, { new_label?, patterns? }) // PUT
api.deleteDescriptionRule(label)                          // DELETE
api.descriptionSuggestions(limit?)                        // GET /description-suggestions
api.applyDescriptionRules(rules[])                        // POST /description-rules/apply
```

`TransactionList` shape: `{ total, amount_total, limit, offset, items[] }` — `total` and `amount_total` cover the **full unpaginated query**, not just the current page.

## Date formatting — ALWAYS use these, never raw ISO strings
```typescript
import { formatDate, formatMonth, toIntlLocale } from "@/lib/utils";
const { locale } = useT();
const intlLocale = toIntlLocale(locale);  // "es" → "es-ES", "en" → "en-GB"

formatDate("2024-05-12", intlLocale)   // "12 mayo 2024" / "12 May 2024"
formatMonth("2024-05", intlLocale)     // "mayo 2024" / "May 2024"
```
**Never** render raw `YYYY-MM-DD` or `YYYY-MM` strings to the user.

## i18n — important key collision warning
The `messages/*.json` files have TWO top-level sections that look like "rules":
- `"rules"` — financial health rule translations (savings_rate, emergency_fund, etc.) — used by `translateRule.ts`
- `"rulesPage"` — UI strings for the `/rules` page (title, tabRules, addRule, etc.)

**Do NOT rename or merge these.** Adding a second `"rules"` key would silently overwrite the financial rules translations (JSON duplicate key bug — already fixed once).

## CategoryTree component
```tsx
// Filter mode (with "All" option):
<CategoryTree selected={{ category, subcategory }} onChange={fn} showAll />

// Edit mode (must pick a leaf):
<CategoryTree selected={{ category, subcategory }} onChange={fn} />
```
The taxonomy lives in `CATEGORY_TREE` (exported from `CategoryTree.tsx`) and **must stay in sync** with `config/category_rules.yaml`.

## Transactions page — TanStack Table conventions
- `manualSorting: true` — sort state → `sort_by`/`sort_dir` query params, backend does the ordering
- `columnResizeMode: "onChange"` — live resize with drag handles on `<th>` borders
- Column `id` values that map to backend `sort_by`: `date`, `description`, `category`, `amount` (balance: `enableSorting: false`)
- Edit column id: `_edit` — `enableSorting: false`, `enableResizing: false`
- `meta: { align: "right" }` on `amount` and `balance` columns
- Sticky bottom bar: `fixed bottom-0` — shows total count, `amount_total`, pagination; page body has `pb-16` to avoid overlap

## Invariants
- **No calculations in the frontend** — totals, projections, savings rates come from the backend
- `"use client"` required for any component using hooks or event handlers
- All data fetching in Server Components uses `{ cache: "no-store" }`
- Source badges (`ai`, `manual`, `cache`) only rendered when source **≠ `rule`** (rule is the silent default)
- Income rows (`amount > 0 && !is_reversal`): `bg-green-50`, green bold amount, green category pill
- Expense rows: neutral gray — **no red**, expenses are the majority
