# Backend — agent notes

## Stack
- Python 3.12 — use `python3`, never `python`
- FastAPI + uvicorn, SQLite (stdlib), PyYAML, pydantic-settings, requests (Ollama)
- No MongoDB, no cloud dependencies

## Running
```bash
cd backend
uvicorn main:app --reload --port 8000   # API
python3 etl.py <file.xlsx>              # CLI import
python3 etl.py <file.xlsx> --use-ai    # CLI import with Ollama
```

## Data flow
```
xlsx → BankParser → RawTransaction → normalize() → categorize_transaction() → SqliteStore
```

## Key files
| File | Role |
|---|---|
| `main.py` | FastAPI app, CORS config |
| `api/routes.py` | All endpoints — read this first |
| `api/deps.py` | Settings (pydantic), get_store() |
| `api/models.py` | Pydantic request/response models |
| `db/sqlite_store.py` | All DB access — single source of truth for schema |
| `categorizer/rule_categorizer.py` | Loads rules from config/category_rules.yaml |
| `categorizer/description_cleaner.py` | Loads rules from config/clean_description_rules.yaml |
| `categorizer/ai_categorizer.py` | Ollama wrapper — rules first, AI only for unknowns |
| `parser/bank_parser.py` | Config-driven xlsx parser (YAML per bank) |
| `parser/normalizer.py` | RawTransaction → normalized dict |

## Endpoints
| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/upload` | Upload .xlsx |
| GET | `/api/v1/transactions` | Filters: month, category, bank_id |
| GET | `/api/v1/summary/{month}` | Monthly breakdown |
| GET | `/api/v1/health-score` | 7-rule financial score |
| GET | `/api/v1/months` | Available months |
| POST | `/api/v1/recategorize` | Re-apply rules to all transactions |
| DELETE | `/api/v1/data` | Wipe all data |

## Paths
- DB: `backend/data/finance.db` (gitignored, recreated on first run)
- AI cache: `backend/data/category_cache.db`
- Bank configs: `banks/santander.yaml`
- Category rules: `config/category_rules.yaml`
- Clean description rules: `config/clean_description_rules.yaml`

## Categorization priority (ai_categorizer.py)
1. Rules (rule_categorizer + description_cleaner) — if any match, stop here
2. SQLite cache — result from a previous AI session
3. Ollama — only for descriptions unknown to rules and not cached
4. Rule fallback — if Ollama unavailable

## Schema fields (transactions table)
`id, import_id, bank_id, date, date_value, description, clean_description,
clean_description_source, amount, balance, currency, is_reversal,
category, subcategory, category_source, month, year, raw_json`

## After editing YAML rules
```bash
curl -X POST http://localhost:8000/api/v1/recategorize
# or with AI for unmatched:
curl -X POST "http://localhost:8000/api/v1/recategorize?use_ai=true"
```
