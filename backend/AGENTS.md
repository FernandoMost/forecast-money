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
| `main.py` | FastAPI app, CORS config |
| `api/routes.py` | All endpoints — read this first |
| `api/deps.py` | Settings (pydantic-settings), `get_store()` |
| `api/models.py` | Pydantic request/response models — source of truth for shapes |
| `db/sqlite_store.py` | All DB access — single source of truth for schema |
| `categorizer/rule_categorizer.py` | Loads `config/category_rules.yaml` |
| `categorizer/description_cleaner.py` | Loads `config/clean_description_rules.yaml` |
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
| `PATCH` | `/api/v1/transactions/{id}` | `clean_description`, `category`, `subcategory` | sets `_source='manual'` |
| `GET` | `/api/v1/summary/{month}` | — | monthly income/expenses/savings/by_category |
| `GET` | `/api/v1/health-score` | — | 7-rule analysis |
| `GET` | `/api/v1/months` | — | available months list |
| `GET` | `/api/v1/health` | — | API status check |
| `POST` | `/api/v1/recategorize` | `use_ai` | hot-reloads YAML rules, re-applies to all transactions |
| `DELETE` | `/api/v1/data` | — | wipe all transactions and imports |

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
- DB: `backend/data/finance.db` (gitignored, recreated on first run)
- AI cache: `backend/data/category_cache.db`
- Bank configs: `banks/*.yaml`
- Category rules: `config/category_rules.yaml`
- Clean description rules: `config/clean_description_rules.yaml`

## Categorization priority (ai_categorizer.py)
1. Rules (`rule_categorizer` + `description_cleaner`) — if any match, stop here
2. SQLite cache — result from a previous AI session
3. Ollama — only for descriptions unknown to rules and not cached
4. Rule fallback — if Ollama unavailable

## `category_source` / `clean_description_source` values
| Value | Meaning |
|---|---|
| `rule` | Matched a rule in the YAML (default/silent) |
| `ai` | Set by Ollama |
| `cache` | From previous AI session cache |
| `manual` | Set by the user via `PATCH /transactions/{id}` |

## Schema — transactions table
```
id, import_id, bank_id, date, date_value, description,
clean_description, clean_description_source,
amount, balance, currency, is_reversal,
category, subcategory, category_source,
month, year, raw_json
```

## After editing YAML rules
```bash
curl -X POST http://localhost:8000/api/v1/recategorize
# or with AI for unmatched:
curl -X POST "http://localhost:8000/api/v1/recategorize?use_ai=true"
```
Server reloads the YAML on each call — no restart needed.
