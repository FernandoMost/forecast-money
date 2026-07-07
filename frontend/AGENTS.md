# Frontend — agent notes

## Stack
- Next.js 14, TypeScript, Tailwind CSS
- TanStack Table v8 (`@tanstack/react-table`) — transactions table
- Server Components by default; pages with state/effects must be `"use client"`
- API base: `http://localhost:8000/api/v1` (env: `NEXT_PUBLIC_API_URL`)

## Routes
| Path | File | Type | Notes |
|---|---|---|---|
| `/` | `app/page.tsx` | Server Component | Dashboard — calls `api.dashboard()` |
| `/transactions` | `app/transactions/page.tsx` | Client Component | TanStack Table, sort/filter/paginate |
| `/trends` | `app/trends/page.tsx` | — | Trends view |
| `/upload` | `app/upload/page.tsx` | — | Statement upload |

## Key files
| File | Role |
|---|---|
| `lib/api.ts` | Typed API client — all fetch calls go here |
| `lib/utils.ts` | `formatEur()`, `formatPercent()`, `STATUS_COLORS`, `CATEGORY_COLORS` |
| `components/Nav.tsx` | Top navigation bar |
| `components/CategoryTree.tsx` | Reusable category+subcategory pill selector; also exports `CATEGORY_TREE`, `catLabel()`, `subLabel()` |

## `lib/api.ts` — key types and calls
```typescript
api.dashboard()              // GET /dashboard → DashboardData
api.transactions(params)     // GET /transactions → TransactionList
  // params: month, year, category, subcategory, sort_by, sort_dir, limit, offset
api.patchTransaction(id, {   // PATCH /transactions/{id}
  clean_description, category, subcategory
})
api.months()                 // GET /months → { months: string[] }
api.summary(month)           // GET /summary/{month} → MonthlySummary
api.upload(file, bank, useAi)
api.recategorize(useAi)
```

`TransactionList` shape: `{ total, amount_total, limit, offset, items[] }` — `total` and `amount_total` cover the **full unpaginated query**, not just the current page.

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
