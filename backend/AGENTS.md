# Backend — agent notes

## Stack
- Python 3.12 — use `python3`, never `python`
- FastAPI + uvicorn, SQLite (stdlib), PyYAML, pydantic-settings, requests (Ollama)
- Run commands: see root `AGENTS.md`

## Key files
| File | Role |
|---|---|
| `main.py` | FastAPI app, CORS, startup migrations/seeds (YAML → shared.db, one-shot) |
| `api/routes.py` | Finance endpoints + categories CRUD |
| `api/description_rules.py` | Description rules CRUD + suggestions + strip config |
| `api/category_rules.py` | Category rules CRUD + category suggestion engine |
| `api/backup.py` | AES-256 encrypted backup export/restore (auth.db + shared.db + users/*.db) |
| `api/prorations.py` | Expense proration CRUD (spread one-off expenses across months) |
| `api/deps.py` | Settings, `get_store()`, `get_shared_store()` |
| `api/models.py` | Pydantic request/response models |
| `db/sqlite_store.py` | Per-user DB — schema source of truth |
| `db/shared_store.py` | Shared DB — `description_rules`, `categories`, `category_rules` |
| `db/user_store.py` | Auth DB — `users` table |
| `categorizer/rule_categorizer.py` | Loads category rules from shared.db (YAML = legacy fallback) |
| `categorizer/description_cleaner.py` | Loads rules from shared.db |
| `categorizer/ai_categorizer.py` | Ollama wrapper |
| `parser/bank_parser.py` | Config-driven xlsx+csv parser |
| `parser/normalizer.py` | `RawTransaction` → normalized dict |
| `rules/health_engine.py` | 7 financial rules → 0-100 score; category roles from shared.db |

## API endpoints
All paths prefixed with `/api/v1`. All require auth — `get_store` depends on `get_current_user`.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/upload` | `file`, `bank`, `use_ai` — `.xlsx` and `.csv` |
| `GET` · `DELETE` | `/imports`, `/imports/{id}` | import history |
| `GET` | `/dashboard` | health score + enriched monthly summary |
| `GET` | `/transactions` | `month year category subcategory sort_by sort_dir limit offset uncleaned` — paginated |
| `PATCH` | `/transactions/{id}` | `clean_description category subcategory month`; `month=YYYY-MM` moves tx date to 1st |
| `GET` | `/summary/{month}` | income/expenses/savings/by_category |
| `GET` | `/health-score`, `/health-history` | 7-rule analysis + history |
| `GET` | `/months` | available months list |
| `POST` | `/recategorize` | `use_ai`; reloads rules, preserves `source=manual` |
| `DELETE` | `/data` | wipe all transactions + imports |
| `GET` · `POST` | `/categories` | category tree list / create |
| `PATCH` · `DELETE` | `/categories/{id}` | update / delete category |
| `GET` · `POST` | `/description-rules` | list w/ match counts / create (`label patterns position`) |
| `PUT` · `DELETE` | `/description-rules/{label}` | update (`new_label patterns category_id subcategory_id`) / delete |
| `POST` | `/description-rules/apply` | `rules[]` — save rules + recategorize |
| `GET` | `/description-suggestions` | grouped uncleaned; sorted `total_count DESC, latest_date DESC` |
| `POST` | `/description-suggestions/dismiss`, `/mark-clean` | hide suggestion / mark already clean |
| `GET` · `POST` · `DELETE` | `/description-strip-config` (…`/{id}`) | per-user prefix/suffix stripping |
| `GET` | `/description-strip-suggestions` | suggested prefixes/suffixes |
| `GET` · `POST` | `/category-rules` | list w/ match counts / create (`category subcategory patterns position`) |
| `PUT` · `DELETE` | `/category-rules/{id}` | update / delete |
| `POST` | `/category-rules/apply` | reload rules + recategorize user txs |
| `GET` | `/category-suggestions` | uncategorized txs grouped by clean_description |
| `POST` | `/category-suggestions/dismiss`, `/apply` | hide / assign category (+ optional `create_rule`) |
| `POST` | `/backup/export` | `{password}` → AES-256 zip download (auth.db, shared.db, users/*.db) |
| `POST` | `/backup/restore` | multipart `file` + `password` → full replace, auto-backups current `data/` |
| `GET` | `/transactions/{id}/proration` | modal context: tx + allocation + similar past expenses |
| `PUT` | `/transactions/{id}/proration` | `{months:[YYYY-MM]}` — 422 on income/reversal/<2 months; returns `monthly_amount` |
| `DELETE` | `/transactions/{id}/proration` | idempotent 204 |

## `get_transactions()` signature
```python
get_transactions(
    month=None, year=None, category=None, subcategory=None, bank_id=None,
    uncleaned=False,          # filter WHERE clean_description IS NULL
    sort_by="date", sort_dir="desc",
    limit=100, offset=0
) -> {"total": int, "amount_total": float, "items": list[dict]}
```

## Paths
- Per-user DB: `data/users/{user_id}.db`
- Shared DB: `data/shared.db`
- Auth DB: `data/auth.db`
- AI cache: `data/category_cache.db`
- Bank configs: `banks/*.yaml`
- `config/category_rules.yaml`, `config/clean_description_rules.yaml` ← LEGACY seeds, migrated to shared.db on first startup

## Categorization priority
1. Description rule with linked `category_id` — takes priority over pattern rules
2. Rules (`rule_categorizer` + `description_cleaner`) — if any match, stop
3. SQLite cache — prior AI result
4. Ollama — only for unknowns
5. Rule fallback — if Ollama unavailable

## `category_source` / `clean_description_source` values
| Value | Meaning |
|---|---|
| `rule` | Matched a rule (silent — no badge in UI) |
| `ai` | Set by Ollama |
| `cache` | From prior AI session |
| `manual` | Set by user via PATCH |

## Schema — transactions table
```
id, import_id, bank_id, date, date_value, description,
clean_description, clean_description_source,
amount, balance, currency, is_reversal,
category, subcategory, category_source,
month, year, raw_json
```

## Schemas — shared.db
```
description_rules: id, label (unique), patterns (JSON array), category_id, subcategory_id, position, created_at, updated_at
categories:        id (TEXT PK), name, parent_id, color, role, position, created_at, updated_at
category_rules:    id, category, subcategory, patterns (JSON array), position, created_at, updated_at
```
`categories.role` (income/needs/wants/leisure/fixed/subscriptions/savings/other) drives the health engine.

## Schema — expense_allocations (per-user db)
```
transaction_id (PK REFERENCES transactions), months (JSON "YYYY-MM" array), created_at, updated_at
```
Proration semantics: only expenses (amount<0, no reversal); 100% redistributed equally across
selected months; fragments are computed by `expand_allocations()` at aggregation time — the
transactions table keeps real amounts/balances. Applied in `get_monthly_summary()`,
`get_dashboard_month_summary()` (totals + by_category + leisure) and `HealthEngine.analyze()`.
`tx_count` and `min/max/last_balance` stay real; summaries return `NULL` min/max balance for
proration-only months. `get_transactions()` items include `proration_months`.
Cleanup on `delete_import()` / `clear_all()`.

## Key behaviours
- `bulk_update_categories()` preserves `source='manual'` rows — uses CASE WHEN
- `update_transaction_manual()` uses COALESCE — omitted fields are no-ops; `month=YYYY-MM` also rewrites `date` to `YYYY-MM-01` and `year`
- Rules reloaded via `reload_rules()` after any CRUD op
- Startup one-shot migrations (each skipped if target table non-empty): description rules YAML → shared.db, default category seed (`main.py _DEFAULT_CATEGORIES`), category_rules YAML → shared.db
