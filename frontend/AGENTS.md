# Frontend — agent notes

## Stack
- Next.js 14, TypeScript, Tailwind CSS
- TanStack Table v8 (`@tanstack/react-table`) — transactions table
- `"use client"` required for any page/component using hooks or event handlers
- API base: `http://localhost:8000/api/v1` (env: `NEXT_PUBLIC_API_URL`)

## Routes
| Path | File | Notes |
|---|---|---|
| `/` | `app/page.tsx` | Dashboard |
| `/transactions` | `app/transactions/page.tsx` | TanStack Table, sort/filter/paginate |
| `/trends` | `app/trends/page.tsx` | Trends view |
| `/upload` | `app/upload/page.tsx` | Statement upload |
| `/health` | `app/health/page.tsx` | Financial health score |
| `/categories` | `app/categories/page.tsx` | Tabs: categories CRUD, category rules, category suggestions |
| `/rules` | `app/rules/page.tsx` | Description rules + suggestion/clean/strip tabs |
| `/login` | `app/login/page.tsx` | Auth |

## Key files
| File | Role |
|---|---|
| `lib/api.ts` | Typed API client — all fetch calls |
| `lib/utils.ts` | `formatEur()`, `formatDate()`, `formatDateSlash()`, `formatMonth()`, `toIntlLocale()`, `STATUS_COLORS` |
| `lib/i18n.tsx` | `useT()` → `{ t, locale, setLocale }` |
| `lib/theme.tsx` | `useTheme()` → `{ isDark, toggleTheme }` |
| `lib/translateRule.ts` | Translates health rule IDs into localised strings |
| `components/Nav.tsx` | Top navigation bar |
| `components/CategoryTree.tsx` | Category+subcategory pill selector; taxonomy fetched from `/categories` API; exports `CATEGORY_TREE`, `catLabel()`, `subLabel()`, `invalidateCategoryCache()` |
| `components/Providers.tsx` | Wraps app with i18n + theme providers |
| `messages/es.json` | Spanish strings |
| `messages/en.json` | English strings |

## `lib/api.ts` — key types and calls
```typescript
api.dashboard()
api.transactions(params)       // supports uncleaned:true to filter WHERE clean_description IS NULL
api.patchTransaction(id, {
  clean_description?, category?, subcategory?,
  month?   // YYYY-MM — moves tx date to 1st of that month (any transaction, not just income)
})
api.months()
api.summary(month)
api.upload(file, bank, useAi)
api.recategorize(useAi)
api.descriptionRules()
api.createDescriptionRule(label, patterns, position?)
api.updateDescriptionRule(label, { new_label?, patterns? })
api.deleteDescriptionRule(label)
api.descriptionSuggestions(limit?)   // SuggestionGroup now includes latest_date: string | null
api.applyDescriptionRules(rules[])
api.dismissSuggestion(canonical)
api.markClean(raw, label)
// Categories + category rules + suggestions
api.categories() / createCategory(data) / updateCategory(id, data) / deleteCategory(id)
api.categoryRules() / createCategoryRule(data) / updateCategoryRule(id, data) / deleteCategoryRule(id) / applyCategoryRules()
api.categorySuggestions(limit?) / dismissCategorySuggestion(desc) / applyCategorySuggestion({ clean_description, category, subcategory?, create_rule? })
// Strip config + imports
api.stripConfig() / addStripEntry(type, value) / deleteStripEntry(id) / stripSuggestions()
api.listImports() / deleteImport(id) / clearAllData()
```

`TransactionList`: `{ total, amount_total, limit, offset, items[] }` — `total`/`amount_total` are full unpaginated counts.

## Date formatting — always use these
```typescript
import { formatDate, formatDateSlash, formatMonth, toIntlLocale } from "@/lib/utils";
const intlLocale = toIntlLocale(locale);  // "es" → "es-ES", "en" → "en-GB"

formatDate("2024-05-12", intlLocale)       // "12 mayo 2024" / "12 May 2024"
formatDateSlash("2024-05-12", intlLocale)  // "12/mayo/2024" / "12/May/2024"  ← used in transactions table
formatMonth("2024-05", intlLocale)         // "mayo 2024" / "May 2024"
```
Never render raw `YYYY-MM-DD` or `YYYY-MM` strings.

## i18n — key collision warning
`messages/*.json` has two sections that look like "rules":
- `"rules"` — financial health rule translations — used by `translateRule.ts`
- `"rulesPage"` — UI strings for `/rules` page

**Do NOT rename or merge these.**

## Transactions page — conventions
- `manualSorting: true` — sort state → `sort_by`/`sort_dir` query params
- `columnResizeMode: "onChange"` — live resize
- `sort_by` values: `date`, `description`, `category`, `amount`
- Date column: clicking the date opens `InlineMonthEdit` (available on **all** rows, not just income)
- Edit column: `_edit` — `enableSorting: false`, `enableResizing: false`
- `meta: { align: "right" }` on `amount` and `balance`
- Sticky bottom bar: `fixed bottom-0`, page body has `pb-16`

## Rules page — tabs
- **Reglas**: description rules CRUD
- **Sugerencias**: grouped uncleaned descriptions; sorted by `total_count DESC, latest_date DESC`
- **Limpieza rápida** (`clean`): inline editor for uncleaned transactions; badge count reloads from API (not optimistic decrement) after each save, after applying suggestions, and after mark-clean
- **Strip**: prefix/suffix strip config

## CategoryTree component
```tsx
<CategoryTree selected={{ category, subcategory }} onChange={fn} showAll />  // filter mode
<CategoryTree selected={{ category, subcategory }} onChange={fn} />           // edit mode
```
Taxonomy comes from `GET /categories` (module-level cache, one fetch per session, hardcoded fallback tree). Call `invalidateCategoryCache()` after any category CRUD.

## Invariants
- No calculations in the frontend — totals/projections come from the backend
- Source badges (`ai`, `manual`, `cache`) only shown when source ≠ `rule`
- Income rows (`amount > 0 && !is_reversal`): `bg-green-50`, green bold amount, green category pill
- Expense rows: neutral gray — no red
