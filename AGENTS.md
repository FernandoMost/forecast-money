# Forecast Money — project context for agents

Privacy-first personal finance analyzer. All data stays local by default.

## Architecture in one diagram

```
banks/*.yaml ──► BankParser ──► RawTransaction ──► normalize() ──► categorize() ──► SqliteStore
                 (xlsx + csv)                        normalizer.py   rule + AI        finance.db

SqliteStore ──► FastAPI (backend/) ──► Next.js (frontend/)
                port 8000               port 3000
```

## Repo layout

```
forecast-money/
├── AGENTS.md              ← you are here — global context
├── banks/                 ← per-bank ETL config (YAML, one file per bank)
│   ├── AGENTS.md
│   ├── sample_bank.csv    ← reference CSV for new bank configs
│   ├── sample_bank.yaml   ← annotated reference config (start here)
│   └── santander.yaml     ← real xlsx example with metadata rows
├── config/                ← categorization rules (hot-reloaded, no restart needed)
│   ├── AGENTS.md
│   ├── category_rules.yaml
│   └── clean_description_rules.yaml
├── backend/               ← Python 3.12 / FastAPI
│   ├── AGENTS.md
│   ├── etl.py             ← CLI entry point
│   ├── main.py            ← FastAPI app + CORS
│   ├── api/               ← routes.py, models.py, deps.py
│   ├── categorizer/       ← rule_categorizer, description_cleaner, ai_categorizer
│   ├── db/                ← sqlite_store.py (single source of truth for schema)
│   ├── parser/            ← bank_parser.py (xlsx+csv), normalizer.py
│   └── rules/             ← health_engine.py (7 financial rules → 0-100 score)
├── frontend/              ← Next.js 14, TypeScript, Tailwind, TanStack Table v8
│   ├── AGENTS.md
│   ├── app/               ← page.tsx (dashboard), transactions/, trends/, upload/
│   ├── components/        ← Nav.tsx, CategoryTree.tsx
│   └── lib/               ← api.ts (typed API client), utils.ts
└── docker-compose.yml
```

## Key invariants

- **No hardcoded bank logic** — all column mappings live in `banks/*.yaml`
- **No calculations in the frontend** — aggregations, projections, totals all come from the backend
- **Rules are hot-reloaded** — editing `config/*.yaml` + `POST /api/v1/recategorize` applies changes without restart
- **SQLite only** — no external DB, no cloud dependencies
- `python3` always, never `python`

## Running locally

```bash
# Backend
cd backend && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev   # http://localhost:3000

# ETL (CLI)
cd backend
python3 etl.py ../statement.xlsx              # rule-based
python3 etl.py ../statement.csv --bank mybank # custom bank config
python3 etl.py ../statement.xlsx --use-ai     # Ollama AI categorization
```

## Where things live — quick lookup

| I need to change… | File |
|---|---|
| API endpoint logic | `backend/api/routes.py` |
| Request/response shapes | `backend/api/models.py` |
| DB queries / schema | `backend/db/sqlite_store.py` |
| Financial health rules | `backend/rules/health_engine.py` |
| How bank files are parsed | `backend/parser/bank_parser.py` |
| Category/subcategory taxonomy | `config/category_rules.yaml` + `frontend/components/CategoryTree.tsx` |
| Dashboard page | `frontend/app/page.tsx` |
| Transactions page | `frontend/app/transactions/page.tsx` |
| API client (typed) | `frontend/lib/api.ts` |
| Add a new bank | Copy `banks/sample_bank.yaml`, adjust, run ETL |
