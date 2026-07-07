# Forecast Money

> Privacy-first personal finance analyzer — all data stays on your machine by default.

Built a privacy-first personal finance analyzer in Python/FastAPI that parses real Santander España bank exports, categorizes transactions using local LLM inference via Ollama (llama3) with SQLite deduplication cache, and applies seven financial health rules (savings rate, emergency fund, subscription cap, 50/30/20, lifestyle inflation) to produce a 0–100 health score and prioritized alert list. Exposed via a REST API consumed by a Next.js dashboard. All data stays local — zero external calls.

---

## Project Structure

```
finance-analyzer/
├── banks/
│   ├── sample_bank.csv       # Fictional bank statement — reference for the column structure
│   ├── sample_bank.yaml      # Fully commented reference config — start here for new banks
│   └── santander.yaml        # Real xlsx example with metadata rows
├── backend/
│   ├── parser/               # Config-driven Excel ETL
│   ├── categorizer/          # Rule-based + Ollama AI categorization with SQLite cache
│   ├── rules/                # 7 financial health rules → 0-100 score
│   ├── api/                  # FastAPI routes + Pydantic models
│   ├── db/                   # SqliteStore
│   ├── etl.py                # CLI entry point
│   └── main.py               # FastAPI application
├── frontend/                 # Next.js dashboard (Dashboard, Transactions, Trends, Upload)
├── docker/
│   ├── Dockerfile.backend
│   └── Dockerfile.frontend
└── docker-compose.yml
```

---

## Quick Start — Local Mode

### Prerequisites
- Python 3.12+
- Node.js 20+
- (Optional) [Ollama](https://ollama.ai) with `llama3` for AI categorization

### 1. Backend setup

```bash
cd backend
pip install -r requirements.txt

# Run ETL — defaults to banks/santander.yaml if --bank is omitted
python etl.py ../statement.xlsx

# Specify a different bank config (maps to banks/mybank.yaml)
python etl.py ../statement.csv --bank mybank

# With AI categorization (requires Ollama running locally)
python etl.py ../statement.xlsx --use-ai

# Start the API server
uvicorn main:app --reload --port 8000
# Visit http://localhost:8000/docs for interactive API explorer
```

### 2. Frontend setup

```bash
cd frontend
npm install
npm run dev
# Visit http://localhost:3000
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/upload` | Upload a `.xlsx` or `.csv` bank statement |
| `GET` | `/api/v1/summary/{month}` | Monthly income/expenses/savings breakdown |
| `GET` | `/api/v1/transactions` | Paginated + filtered transaction list |
| `GET` | `/api/v1/health-score` | 7-rule health analysis → 0-100 score |
| `GET` | `/api/v1/months` | Available months with data |
| `GET` | `/api/v1/health` | API status check |

---

## Financial Health Rules

| Rule | Logic | Thresholds |
|------|-------|------------|
| 10% Savings Rule | Monthly savings ≥ 10% of net income | <5% → red, 5–10% → amber, ≥10% → green |
| Emergency Fund | Balance covers N months of fixed costs | <1 month → red, 1–3 → amber, ≥3 → green |
| Subscription Cap | Subscriptions ≤ 15% of income | >22% → red, 15–22% → amber |
| Leisure Cap | Restaurants + entertainment ≤ 20% | >30% → red, 20–30% → amber |
| Outlier Detector | Transactions > 2× 3-month category avg | >2 outliers → red |
| 50/30/20 Rule | Needs ≤50%, wants ≤30%, savings ≥20% | Each violation → amber/red |
| Lifestyle Inflation | Avg spend growth >5% vs prior period | >10% without income growth → red |

---

## Adding a New Bank

Supports both **xlsx** and **csv**. All structural knowledge lives in a YAML config — no code changes needed.

| File | Purpose |
|------|---------|
| `banks/sample_bank.csv` | Minimal fictional statement — reference for the expected column layout |
| `banks/sample_bank.yaml` | Annotated reference config — start here |
| `banks/santander.yaml` | Real xlsx example with metadata rows above the transaction table |

```bash
cp banks/sample_bank.yaml banks/mybank.yaml
# edit banks/mybank.yaml, then:
python etl.py statement.csv --bank mybank
```

Key fields to adjust:

| Field | Notes |
|-------|-------|
| `file.extension` | `csv` or `xlsx` |
| `sheet.header_row` / `data_start_row` | 1-based; rows above `header_row` are skipped |
| `columns.*` | 1-based column index for each logical field |
| `parsing.date_format` | `strptime` string — e.g. `%Y-%m-%d`, `%d/%m/%Y` |
| `parsing.amount_decimal_separator` | `.` or `,` |
| `sheet.metadata` | xlsx only — extract account/balance from cells above the table (see `santander.yaml`) |

---

## Privacy

- **Local mode is the default.** No data leaves your machine.
- No telemetry, analytics, or external API calls unless you explicitly configure them.
- AI categorization uses [Ollama](https://ollama.ai) running locally. Claude API / OpenAI are never called by default.
- SQLite database and output files stay on your filesystem.
- `sample_export.xlsx` and actual bank files are excluded from `.gitignore` by default.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| ETL / Backend | Python 3.12, FastAPI, Pydantic v2 |
| Data parsing | openpyxl (xlsx), csv stdlib (csv), PyYAML (config-driven) |
| AI categorization | Ollama + llama3 (local) |
| Local DB | SQLite via stdlib |
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Recharts |
| DevOps | Docker |
