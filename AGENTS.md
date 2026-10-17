# Forecast Money — project context for agents

Privacy-first personal finance analyzer. All data stays local.

## Architecture

```
banks/*.yaml ──► BankParser ──► RawTransaction ──► normalize() ──► categorize() ──► SqliteStore
                 (xlsx + csv)                        normalizer.py   rule + AI        users/{id}.db

SqliteStore ──► FastAPI (backend/) ──► Next.js (frontend/)
                port 8000               port 3000
```

## Repo layout

```
forecast-money/
├── banks/          ← per-bank ETL config (YAML); sample_bank.yaml is the annotated reference
├── config/         ← legacy YAML seeds → migrated to shared.db on first startup
├── backend/        ← Python 3.12 / FastAPI
│   ├── main.py     ← app + CORS + startup migration/seeds
│   ├── api/        ← routes.py, category_rules.py, description_rules.py, backup.py, models.py, deps.py
│   ├── categorizer/← rule_categorizer, description_cleaner, ai_categorizer
│   ├── db/         ← sqlite_store.py, shared_store.py, user_store.py
│   ├── parser/     ← bank_parser.py, normalizer.py
│   ├── auth/       ← routes.py, models.py, security.py
│   └── rules/      ← health_engine.py (7 rules → 0-100 score)
├── frontend/       ← Next.js 14, TypeScript, Tailwind, TanStack Table v8
│   ├── app/        ← page.tsx (dashboard), transactions/, trends/, upload/,
│   │                  health/, categories/, rules/, login/
│   ├── components/ ← Nav.tsx, CategoryTree.tsx, Providers.tsx
│   ├── lib/        ← api.ts, utils.ts, i18n.tsx, theme.tsx, translateRule.ts
│   └── messages/   ← es.json, en.json
└── docker-compose.yml
```

## Key invariants

- **No hardcoded bank logic** — all column mappings live in `banks/*.yaml`
- **No calculations in the frontend** — aggregations, projections, totals come from the backend
- **Description rules live in `data/shared.db`** — NOT the YAML (legacy). Edit via `/rules` UI or API.
- **Categories + category rules live in `data/shared.db`** — seeded from YAML/defaults on first startup; edit via `/categories` UI or API.
- **SQLite only** — no external DB, no cloud dependencies
- **Multi-user** — each user has `data/users/{user_id}.db`; shared rules in `data/shared.db`; auth in `data/auth.db`
- **Auth** — httpOnly JWT cookie (`access_token`). All finance endpoints require auth.
- `python3` always, never `python`

## DB files

| File | Contents | Class |
|---|---|---|
| `data/auth.db` | users table | `UserStore` |
| `data/shared.db` | description_rules, categories, category_rules | `SharedStore` |
| `data/users/{id}.db` | transactions, imports, health_score_history | `SqliteStore` |

## Running locally

```bash
# Backend
cd backend && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev   # http://localhost:3000

# ETL (CLI)
cd backend
python3 etl.py ../statement.xlsx              # rule-based
python3 etl.py ../statement.csv --bank mybank
python3 etl.py ../statement.xlsx --use-ai     # Ollama AI categorization
```

## Where things live — quick lookup

| I need to change… | File |
|---|---|
| API endpoint logic | `backend/api/routes.py` |
| Description rules CRUD + suggestion engine | `backend/api/description_rules.py` |
| Category rules CRUD + category suggestions | `backend/api/category_rules.py` |
| Request/response shapes | `backend/api/models.py` |
| DB queries / schema (per-user) | `backend/db/sqlite_store.py` |
| Shared DB (rules + categories) | `backend/db/shared_store.py` |
| Auth DB (users) | `backend/db/user_store.py` |
| Financial health rules | `backend/rules/health_engine.py` |
| Bank file parsing | `backend/parser/bank_parser.py` |
| Backup export/restore (AES-256 ZIP) | `backend/api/backup.py` |
| Category/subcategory taxonomy | `categories` table in shared.db (seeded in `main.py`), served via `/api/v1/categories` |
| Description cleaning logic | `backend/categorizer/description_cleaner.py` |
| Dashboard page | `frontend/app/page.tsx` |
| Transactions page | `frontend/app/transactions/page.tsx` |
| Rules page (description rules UI) | `frontend/app/rules/page.tsx` |
| API client (typed) | `frontend/lib/api.ts` |
| Date/currency formatting | `frontend/lib/utils.ts` |
| i18n strings | `frontend/messages/es.json` + `en.json` |
| Add a new bank | Copy `banks/sample_bank.yaml`, adjust, run ETL |
