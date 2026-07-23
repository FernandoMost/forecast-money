# Forecast Money

> Privacy-first personal finance analyzer — all data stays on your machine.

Parse real bank exports (xlsx/csv), categorize transactions with rules or local AI (Ollama), and get a 0–100 financial health score with prioritized alerts. Multi-user, fully local, no cloud.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLite |
| AI categorization | Ollama (local) — optional |
| Frontend | Next.js 14, TypeScript, Tailwind CSS, TanStack Table v8 |
| Auth | httpOnly JWT cookie |
| DevOps | Docker Compose |

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- (Optional) [Ollama](https://ollama.ai) for AI categorization

### Backend

```bash
cd backend
pip install -r requirements.txt

# Import a bank statement (defaults to banks/santander.yaml)
python3 etl.py ../statement.xlsx
python3 etl.py ../statement.csv --bank mybank
python3 etl.py ../statement.xlsx --use-ai   # requires Ollama

# Start API
uvicorn main:app --reload --port 8000
# Docs: http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

### Docker

```bash
docker-compose up
```

---

## Features

- **Config-driven bank parser** — add any bank by writing a YAML file, no code changes
- **Rule-based categorization** — hot-reloaded YAML rules
- **AI categorization** — Ollama (llama3) with SQLite dedup cache; rules always take priority
- **Description cleaning** — normalize messy bank descriptions via rules or quick inline editor
- **Month assignment** — move any transaction to a different accounting month (useful for salaries paid at month-end or recurring bills that straddle months)
- **Financial health score** — 7 rules → 0-100 score with amber/red alerts
- **Multi-user** — per-user SQLite databases, shared description rules
- **i18n** — Spanish / English

---

## Financial Health Rules

| Rule | Threshold |
|---|---|
| Savings rate ≥ 10% of net income | <5% → red |
| Emergency fund ≥ 3 months fixed costs | <1 month → red |
| Subscriptions ≤ 15% of income | >22% → red |
| Leisure ≤ 20% of income | >30% → red |
| Outlier detector (>2× 3-month avg) | >2 outliers → red |
| 50/30/20 rule | per-bucket violations |
| Lifestyle inflation ≤ 5% avg spend growth | >10% without income growth → red |

---

## Adding a New Bank

All structural knowledge lives in a YAML config — no code changes needed.

```bash
cp banks/sample_bank.yaml banks/mybank.yaml
# Edit mybank.yaml: file.extension, columns.*, parsing.date_format, etc.
python3 etl.py statement.csv --bank mybank
```

See `banks/sample_bank.yaml` for the fully annotated reference.

---

## Privacy

- No data leaves your machine by default
- No telemetry or external API calls
- AI via Ollama running locally
- SQLite files stay on your filesystem
