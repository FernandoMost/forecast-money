# Forecast Money

> Privacy-first personal finance analyzer — all data stays on your machine by default.

Built a privacy-first personal finance analyzer in Python/FastAPI that parses real Santander España bank exports, categorizes transactions using local LLM inference via Ollama (llama3) with SQLite deduplication cache, and applies seven financial health rules (savings rate, emergency fund, subscription cap, 50/30/20, lifestyle inflation) to produce a 0–100 health score and prioritized alert list. Exposed via a REST API consumed by a Next.js dashboard. All data stays local — zero external calls.

---

## Project Structure

```
finance-analyzer/
├── banks/
│   └── santander.yaml        # Column mapping config — add new banks without touching code
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

# Run ETL on your bank statement (rule-based categorization)
python etl.py ../sample_export.xlsx

# With AI categorization (requires Ollama running locally)
python etl.py ../sample_export.xlsx --use-ai

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
| `POST` | `/api/v1/upload` | Upload a `.xlsx` bank statement |
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

1. Copy `banks/santander.yaml` → `banks/mybank.yaml`
2. Adjust `header_row`, `data_start_row`, column indices, date format, and amount parsing config
3. Run: `python etl.py export.xlsx --bank mybank`

No code changes required.

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
| Data parsing | openpyxl, PyYAML (config-driven) |
| AI categorization | Ollama + llama3 (local) |
| Local DB | SQLite via stdlib |
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Recharts |
| DevOps | Docker |
