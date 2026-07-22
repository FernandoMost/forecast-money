"""
etl.py — Local ETL entry point (Phase 1 MVP, CLI mode)

Usage:
    python etl.py <path/to/export.xlsx> [--bank santander] [--use-ai] [--out-dir ./output]

Outputs:
    output/summary_YYYY-MM.json     — per-month summary + health score
    output/report_YYYY-MM.txt       — plain text financial health report
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add backend directory to Python path so imports work from project root
sys.path.insert(0, str(Path(__file__).parent))

from parser.bank_parser import BankParser
from parser.normalizer import normalize
from categorizer.rule_categorizer import categorize_transaction
from categorizer.ai_categorizer import AiCategorizer
from db.sqlite_store import SqliteStore
from rules.health_engine import HealthEngine


def run_etl(
    file_path: Path,
    bank_config: Path,
    use_ai: bool,
    out_dir: Path,
    db_path: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------
    # 1. Parse Excel
    # ---------------------------------------------------------------
    print(f"[ETL] Parsing {file_path.name} with config {bank_config.name}...")
    parser = BankParser(bank_config)
    result = parser.parse(file_path)

    if result.parse_warnings:
        for w in result.parse_warnings:
            print(f"  [WARN] {w}")

    print(f"[ETL] Parsed {len(result.transactions)} transactions.")
    meta = result.metadata
    print(f"      Account: {meta.account_number}  Holder: {meta.account_holder}")
    print(f"      Current balance: {meta.current_balance}  Export date: {meta.export_date}")

    # ---------------------------------------------------------------
    # 2. Normalize
    # ---------------------------------------------------------------
    normalized = [normalize(raw, meta.bank_id, parser.strip_description_prefixes) for raw in result.transactions]
    print(f"[ETL] Normalized {len(normalized)} transactions.")

    # ---------------------------------------------------------------
    # 3. Categorize
    # ---------------------------------------------------------------
    if use_ai:
        print("[ETL] Categorizing with AI (Ollama) + rule fallback...")
        ai = AiCategorizer(cache_path=db_path.parent / "category_cache.db")
        categorized = [ai.categorize_transaction(tx) for tx in normalized]
    else:
        print("[ETL] Categorizing with rule-based engine...")
        categorized = [categorize_transaction(tx) for tx in normalized]

    src_counts: dict[str, int] = {}
    for tx in categorized:
        src = tx.get("category_source", "unknown")
        src_counts[src] = src_counts.get(src, 0) + 1
    print(f"[ETL] Category sources: {src_counts}")

    # ---------------------------------------------------------------
    # 4. Persist to SQLite
    # ---------------------------------------------------------------
    store = SqliteStore(db_path)
    import_id = uuid.uuid4().hex
    inserted = store.upsert_transactions(categorized, import_id)
    store.save_import(
        import_id=import_id,
        bank_id=meta.bank_id,
        filename=file_path.name,
        tx_count=inserted,
        metadata={
            "account_number": meta.account_number,
            "account_holder": meta.account_holder,
            "current_balance": meta.current_balance,
            "export_date": meta.export_date,
        },
    )
    print(f"[ETL] Saved {inserted} new transactions (import_id={import_id}).")

    # ---------------------------------------------------------------
    # 5. Run health engine
    # ---------------------------------------------------------------
    print("[ETL] Running financial health engine...")
    engine = HealthEngine(current_balance=meta.current_balance)
    all_txs = store.get_all_transactions_for_rules()
    health = engine.analyze(all_txs)

    print(f"\n{'='*60}")
    print(f"  FINANCIAL HEALTH SCORE: {health.overall_score}/100  (Grade: {health.grade})")
    print(f"{'='*60}")

    # ---------------------------------------------------------------
    # 6. Write JSON summary
    # ---------------------------------------------------------------
    available_months = store.get_available_months()
    all_summaries = {m: store.get_monthly_summary(m) for m in available_months}

    json_out = out_dir / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(),
                "account": {
                    "holder": meta.account_holder,
                    "account_number": meta.account_number,
                    "bank": meta.bank_name,
                    "current_balance": meta.current_balance,
                },
                "health": {
                    "score": health.overall_score,
                    "grade": health.grade,
                    "months_analyzed": health.months_analyzed,
                    "summary": health.summary,
                    "rules": [
                        {
                            "rule_id": r.rule_id,
                            "name": r.name,
                            "status": r.status,
                            "score": r.score,
                            "message": r.message,
                            "details": r.details,
                        }
                        for r in health.rules
                    ],
                    "alerts": [
                        {
                            "rule_id": r.rule_id,
                            "name": r.name,
                            "status": r.status,
                            "message": r.message,
                        }
                        for r in health.alerts
                    ],
                },
                "monthly_summaries": all_summaries,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"[ETL] JSON summary written to {json_out}")

    # ---------------------------------------------------------------
    # 7. Write plain text report
    # ---------------------------------------------------------------
    txt_out = out_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with txt_out.open("w", encoding="utf-8") as f:
        f.write(_render_text_report(health, all_summaries, meta))
    print(f"[ETL] Text report written to {txt_out}")

    # Print alerts to console
    if health.alerts:
        print(f"\n[!] {len(health.alerts)} alert(s):")
        for alert in health.alerts:
            icon = "🔴" if alert.status == "red" else "🟡"
            print(f"  {icon} [{alert.status.upper()}] {alert.name}: {alert.message}")
    else:
        print("\n[OK] No alerts — all rules green.")


def _render_text_report(health, monthly_summaries: dict, meta) -> str:
    lines = [
        "=" * 70,
        "  PERSONAL FINANCE HEALTH REPORT",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Account holder: {meta.account_holder or 'Unknown'}",
        f"  Bank: {meta.bank_name}",
        f"  Current balance: {meta.current_balance:.2f} EUR" if meta.current_balance else "  Current balance: Unknown",
        "=" * 70,
        "",
        f"  OVERALL HEALTH SCORE: {health.overall_score}/100  (Grade: {health.grade})",
        f"  Months analyzed: {', '.join(health.months_analyzed[-6:])}",
        "",
        f"  Total income:   €{health.summary['total_income']:>10,.2f}",
        f"  Total expenses: €{health.summary['total_expenses']:>10,.2f}",
        f"  Net savings:    €{health.summary['net_savings']:>10,.2f}",
        "",
        "-" * 70,
        "  RULE-BY-RULE BREAKDOWN",
        "-" * 70,
    ]

    status_icon = {"green": "[OK]  ", "amber": "[WARN]", "red":   "[ERR] "}
    for rule in health.rules:
        icon = status_icon.get(rule.status, "      ")
        lines.append(f"  {icon} {rule.name:<35} score: {rule.score:>5.1f}/100")
        lines.append(f"         {rule.message}")
        lines.append("")

    if health.alerts:
        lines += [
            "-" * 70,
            "  PRIORITIZED ALERTS",
            "-" * 70,
        ]
        for i, alert in enumerate(health.alerts, 1):
            lines.append(f"  {i}. [{alert.status.upper()}] {alert.name}")
            lines.append(f"     {alert.message}")
            lines.append("")

    lines += [
        "-" * 70,
        "  MONTHLY SUMMARY (last 6 months)",
        "-" * 70,
    ]
    for month in sorted(monthly_summaries.keys())[-6:]:
        s = monthly_summaries[month]
        lines.append(
            f"  {month}  income: €{s['total_income']:>8,.2f}  "
            f"expenses: €{s['total_expenses']:>8,.2f}  "
            f"savings: €{s['net_savings']:>8,.2f}  "
            f"({s['savings_rate']:.1f}%)"
        )

    lines += ["", "=" * 70]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Forecast Money — local ETL")
    parser.add_argument("file", type=Path, help="Path to bank statement Excel file")
    parser.add_argument("--bank", default="santander", help="Bank config name (without .yaml)")
    parser.add_argument("--use-ai", action="store_true", help="Use Ollama AI categorizer (requires Ollama running)")
    parser.add_argument("--out-dir", type=Path, default=Path("output"), help="Output directory")
    parser.add_argument("--db", type=Path, default=Path("data/finance.db"), help="SQLite database path")
    args = parser.parse_args()

    banks_dir = Path(__file__).parent.parent / "banks"
    bank_config = banks_dir / f"{args.bank}.yaml"

    if not bank_config.exists():
        print(f"[ERROR] Bank config not found: {bank_config}")
        sys.exit(1)
    if not args.file.exists():
        print(f"[ERROR] File not found: {args.file}")
        sys.exit(1)

    run_etl(
        file_path=args.file,
        bank_config=bank_config,
        use_ai=args.use_ai,
        out_dir=args.out_dir,
        db_path=args.db,
    )


if __name__ == "__main__":
    main()
