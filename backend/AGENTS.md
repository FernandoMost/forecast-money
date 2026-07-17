# Backend — agent notes

## Stack
- Python 3.12 — use `python3`, never `python`
- FastAPI + uvicorn, SQLite (stdlib), PyYAML, pydantic-settings, requests (Ollama)
- No MongoDB, no cloud dependencies

## Running
```bash
cd backend
uvicorn main:app --reload --port 8000        # API server
python3 etl.py ../statement.xlsx             # CLI import (default: santander)
python3 etl.py ../statement.csv --bank mybank # custom bank config
python3 etl.py ../statement.xlsx --use-ai    # with Ollama AI categorization
```

## Data flow
```
xlsx/csv → BankParser → RawTransaction → normalize() → categorize_transaction() → SqliteStore
```
`BankParser` detects `file.extension` from the bank YAML — routes to `_parse_xlsx()` or `_parse_csv()`. Both use identical 1-based column index mapping.

## Key files
| File | Role |
|---|---|
| `main.py` | FastAPI app, CORS config, startup migration (YAML → shared.db) |
| `api/routes.py` | All finance endpoints — read this first |
| `api/description_rules.py` | CRUD for description rules + suggestion engine |
| `api/deps.py` | Settings (pydantic-settings), `get_store()`, `get_shared_store()` |
| `api/models.py` | Pydantic request/response models — source of truth for shapes |
| `db/sqlite_store.py` | Per-user DB access — single source of truth for schema |
| `db/shared_store.py` | Shared DB — `description_rules` table, YAML migration |
| `db/user_store.py` | Auth DB — `users` table |
| `categorizer/rule_categorizer.py` | Loads `config/category_rules.yaml` |
| `categorizer/description_cleaner.py` | Loads rules from `data/shared.db` (NOT YAML) |
| `categorizer/ai_categorizer.py` | Ollama wrapper — rules first, AI only for unknowns |
| `parser/bank_parser.py` | Config-driven xlsx+csv parser |
| `parser/normalizer.py` | `RawTransaction` → normalized dict |
| `rules/health_engine.py` | 7 financial rules → 0-100 score |

## API endpoints
| Method | Path | Key params | Notes |
|---|---|---|---|
| `POST` | `/api/v1/upload` | `file`, `bank`, `use_ai` | accepts `.xlsx` and `.csv` |
| `GET` | `/api/v1/dashboard` | — | health score + primary/secondary month enriched summary + staleness |
| `GET` | `/api/v1/transactions` | `month`, `year`, `category`, `subcategory`, `sort_by`, `sort_dir`, `limit`, `offset` | paginated; returns `total`, `amount_total`, `items` |
| `PATCH` | `/api/v1/transactions/{id}` | `clean_description`, `category`, `subcategory` | sets `_source='manual'`; uses COALESCE — omitted fields are preserved |
| `GET` | `/api/v1/summary/{month}` | — | monthly income/expenses/savings/by_category |
| `GET` | `/api/v1/health-score` | — | 7-rule analysis |
| `GET` | `/api/v1/months` | — | available months list |
| `GET` | `/api/v1/health` | — | API status check |
| `POST` | `/api/v1/recategorize` | `use_ai` | hot-reloads rules, re-applies to all transactions; preserves `source=manual` |
| `DELETE` | `/api/v1/data` | — | wipe all transactions and imports |
| `GET` | `/api/v1/description-rules` | — | list rules with match counts |
| `POST` | `/api/v1/description-rules` | `label`, `patterns`, `position` | add rule to shared.db |
| `PUT` | `/api/v1/description-rules/{label}` | `new_label`, `patterns` | update rule |
| `DELETE` | `/api/v1/description-rules/{label}` | — | delete rule |
| `GET` | `/api/v1/description-suggestions` | `limit` | grouped uncleaned descriptions with suggested label+patterns |
| `POST` | `/api/v1/description-rules/apply` | `rules[]` | save rules + recategorize in one call |

## sqlite_store.get_transactions() signature
```python
get_transactions(
    month=None, year=None, category=None, subcategory=None, bank_id=None,
    sort_by="date", sort_dir="desc",   # sort_by whitelist: date|amount|balance|description|category|month
    limit=100, offset=0
) -> {"total": int, "amount_total": float, "items": list[dict]}
```
`total` and `amount_total` are for the full (unpaginated) query — use them for pagination controls and footers.

## Paths
- Per-user DB: `backend/data/users/{user_id}.db`
- Shared DB: `backend/data/shared.db` ← description_rules live here
- Auth DB: `backend/data/auth.db`
- AI cache: `backend/data/category_cache.db`
- Bank configs: `banks/*.yaml`
- Category rules: `config/category_rules.yaml`
- Clean description rules: `config/clean_description_rules.yaml` ← LEGACY, migrated to shared.db on startup

## Categorization priority (ai_categorizer.py)
1. Rules (`rule_categorizer` + `description_cleaner`) — if any match, stop here
2. SQLite cache — result from a previous AI session
3. Ollama — only for descriptions unknown to rules and not cached
4. Rule fallback — if Ollama unavailable

## `category_source` / `clean_description_source` values
| Value | Meaning |
|---|---|
| `rule` | Matched a rule in shared.db (default/silent — no badge in UI) |
| `ai` | Set by Ollama |
| `cache` | From previous AI session cache |
| `manual` | Set by the user via `PATCH /transactions/{id}` |

## Schema — transactions table (per-user DB)
```
id, import_id, bank_id, date, date_value, description,
clean_description, clean_description_source,
amount, balance, currency, is_reversal,
category, subcategory, category_source,
month, year, raw_json
```

## Schema — description_rules table (shared.db)
```
id (autoincrement), label (unique), patterns (JSON array), position, created_at, updated_at
```

## Key behaviours to remember
- `bulk_update_categories()` (recategorize) **preserves** rows with `source='manual'` — uses CASE WHEN
- `update_transaction_manual()` uses `COALESCE(?, field)` for all fields — omitting a field is a no-op
- Description rules are loaded into memory at startup and reloaded via `reload_rules()` after any CRUD op
- Startup event in `main.py` auto-migrates YAML → shared.db if the table is empty (one-shot)
