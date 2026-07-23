# Backend — agent notes

## Stack
- Python 3.12 — use `python3`, never `python`
- FastAPI + uvicorn, SQLite (stdlib), PyYAML, pydantic-settings, requests (Ollama)

## Running
```bash
cd backend
uvicorn main:app --reload --port 8000
python3 etl.py ../statement.xlsx
python3 etl.py ../statement.csv --bank mybank
python3 etl.py ../statement.xlsx --use-ai
```

## Key files
| File | Role |
|---|---|
| `main.py` | FastAPI app, CORS, startup migration (YAML → shared.db) |
| `api/routes.py` | All finance endpoints |
| `api/description_rules.py` | Description rules CRUD + suggestion engine |
| `api/deps.py` | Settings, `get_store()`, `get_shared_store()` |
| `api/models.py` | Pydantic request/response models |
| `db/sqlite_store.py` | Per-user DB — schema source of truth |
| `db/shared_store.py` | Shared DB — `description_rules` table |
| `db/user_store.py` | Auth DB — `users` table |
| `categorizer/rule_categorizer.py` | Loads `config/category_rules.yaml` |
| `categorizer/description_cleaner.py` | Loads rules from `data/shared.db` |
| `categorizer/ai_categorizer.py` | Ollama wrapper |
| `parser/bank_parser.py` | Config-driven xlsx+csv parser |
| `parser/normalizer.py` | `RawTransaction` → normalized dict |
| `rules/health_engine.py` | 7 financial rules → 0-100 score |

## API endpoints
| Method | Path | Key params | Notes |
|---|---|---|---|
| `POST` | `/api/v1/upload` | `file`, `bank`, `use_ai` | `.xlsx` and `.csv` |
| `GET` | `/api/v1/dashboard` | — | health score + enriched monthly summary |
| `GET` | `/api/v1/transactions` | `month`, `year`, `category`, `subcategory`, `sort_by`, `sort_dir`, `limit`, `offset`, `uncleaned` | paginated |
| `PATCH` | `/api/v1/transactions/{id}` | `clean_description`, `category`, `subcategory`, `month` | `month=YYYY-MM` moves tx date to 1st of that month |
| `GET` | `/api/v1/summary/{month}` | — | income/expenses/savings/by_category |
| `GET` | `/api/v1/health-score` | — | 7-rule analysis |
| `GET` | `/api/v1/months` | — | available months list |
| `POST` | `/api/v1/recategorize` | `use_ai` | hot-reloads rules, re-applies; preserves `source=manual` |
| `DELETE` | `/api/v1/data` | — | wipe all transactions |
| `GET` | `/api/v1/description-rules` | — | list rules with match counts |
| `POST` | `/api/v1/description-rules` | `label`, `patterns`, `position` | add rule |
| `PUT` | `/api/v1/description-rules/{label}` | `new_label`, `patterns` | update rule |
| `DELETE` | `/api/v1/description-rules/{label}` | — | delete rule |
| `GET` | `/api/v1/description-suggestions` | `limit` | grouped uncleaned descriptions; sorted by `total_count DESC, latest_date DESC`; returns `latest_date` per group |
| `POST` | `/api/v1/description-rules/apply` | `rules[]` | save rules + recategorize |
| `POST` | `/api/v1/description-suggestions/dismiss` | `description` | hide suggestion |
| `POST` | `/api/v1/description-suggestions/mark-clean` | `description`, `label` | mark as already clean |

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
- Category rules: `config/category_rules.yaml`
- Clean description rules: `config/clean_description_rules.yaml` ← LEGACY, migrated on startup

## Categorization priority
1. Rules (`rule_categorizer` + `description_cleaner`) — if any match, stop
2. SQLite cache — prior AI result
3. Ollama — only for unknowns
4. Rule fallback — if Ollama unavailable

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

## Schema — description_rules (shared.db)
```
id, label (unique), patterns (JSON array), position, created_at, updated_at
```

## Key behaviours
- `bulk_update_categories()` preserves `source='manual'` rows — uses CASE WHEN
- `update_transaction_manual()` uses COALESCE — omitted fields are no-ops; `month=YYYY-MM` also rewrites `date` to `YYYY-MM-01` and `year`
- Description rules reloaded via `reload_rules()` after any CRUD op
- Startup auto-migrates YAML → shared.db if table is empty (one-shot)
