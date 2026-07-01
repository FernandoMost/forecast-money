"""
rules/health_engine.py

Financial health scoring engine.
Implements 7 rules, produces a 0-100 score, and a list of prioritized alerts.

Each rule returns a RuleResult with:
  - rule_id       str
  - name          str
  - status        'green' | 'amber' | 'red'
  - score         float  (0-100 contribution from this rule)
  - message       str    (human-readable explanation)
  - details       dict   (raw numbers for the UI)
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    rule_id: str
    name: str
    status: str          # 'green' | 'amber' | 'red'
    score: float         # 0-100
    message: str
    details: dict = field(default_factory=dict)
    priority: int = 0    # lower = more urgent alert


@dataclass
class HealthReport:
    overall_score: float
    grade: str           # A / B / C / D / F
    rules: list[RuleResult]
    alerts: list[RuleResult]     # only amber/red, sorted by priority
    months_analyzed: list[str]
    summary: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group_by_month(transactions: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for tx in transactions:
        groups[tx["month"]].append(tx)
    return dict(groups)


def _income(txs: list[dict]) -> float:
    return sum(tx["amount"] for tx in txs if tx["amount"] > 0 and not tx.get("is_reversal"))


def _expenses(txs: list[dict]) -> float:
    return abs(sum(tx["amount"] for tx in txs if tx["amount"] < 0 and not tx.get("is_reversal")))


def _cat_expenses(txs: list[dict], *categories: str) -> float:
    return abs(sum(
        tx["amount"]
        for tx in txs
        if tx["amount"] < 0 and tx.get("category") in categories and not tx.get("is_reversal")
    ))


def _score_from_ratio(actual: float, target: float, higher_is_better: bool = True) -> float:
    """Map actual/target ratio to 0-100 score."""
    if target == 0:
        return 100.0
    ratio = actual / target
    if higher_is_better:
        return min(100.0, ratio * 100)
    else:
        # lower is better (e.g. expense ratios)
        return max(0.0, (2 - ratio) * 50)


def _grade(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------

def rule_savings_rate(monthly: dict[str, list[dict]]) -> RuleResult:
    """10% savings rule: monthly savings >= 10% of net income."""
    TARGET = 0.10
    rates = []
    for month, txs in monthly.items():
        inc = _income(txs)
        if inc == 0:
            continue
        exp = _expenses(txs)
        rate = (inc - exp) / inc
        rates.append(rate)

    if not rates:
        return RuleResult("savings_rate", "10% Savings Rule", "red", 0, "No income data found.", priority=1)

    avg_rate = statistics.mean(rates)
    months_green = sum(1 for r in rates if r >= TARGET)
    months_total = len(rates)

    if avg_rate >= TARGET:
        status = "green"
        score = min(100.0, (avg_rate / TARGET) * 80 + 20)
        msg = f"Good — avg savings rate {avg_rate:.1%} over {months_total} months."
    elif avg_rate >= 0.05:
        status = "amber"
        score = 50.0
        msg = f"Borderline — avg savings rate {avg_rate:.1%} (target ≥10%). {months_green}/{months_total} months on target."
    else:
        status = "red"
        score = max(0.0, avg_rate / TARGET * 40)
        msg = f"Critical — avg savings rate {avg_rate:.1%} (target ≥10%). Only {months_green}/{months_total} months on target."

    return RuleResult(
        "savings_rate", "10% Savings Rule", status, round(score, 1), msg, priority=1,
        details={"avg_rate": round(avg_rate, 4), "target": TARGET, "months_analyzed": months_total, "months_on_target": months_green},
    )


def rule_emergency_fund(monthly: dict[str, list[dict]], current_balance: float | None) -> RuleResult:
    """Emergency fund: balance should cover 3-6 months of fixed costs."""
    if current_balance is None or current_balance <= 0:
        return RuleResult("emergency_fund", "Emergency Fund", "red", 0,
                          "Current balance unknown — cannot assess emergency fund.", priority=2)

    fixed_cats = {"housing", "subscriptions"}
    monthly_fixed_costs = []
    for txs in monthly.values():
        fixed = _cat_expenses(txs, *fixed_cats)
        if fixed > 0:
            monthly_fixed_costs.append(fixed)

    if not monthly_fixed_costs:
        return RuleResult("emergency_fund", "Emergency Fund", "amber", 50,
                          "No fixed cost data to assess emergency fund.", priority=2)

    avg_fixed = statistics.mean(monthly_fixed_costs)
    months_covered = current_balance / avg_fixed if avg_fixed > 0 else 99

    if months_covered >= 6:
        status, score, msg = "green", 100.0, f"Excellent — balance covers {months_covered:.1f} months of fixed costs (≥6 target)."
    elif months_covered >= 3:
        status, score, msg = "green", 75.0, f"Good — balance covers {months_covered:.1f} months of fixed costs (3–6 target)."
    elif months_covered >= 1:
        status, score, msg = "amber", 40.0, f"Low — balance covers only {months_covered:.1f} months of fixed costs (target 3–6)."
    else:
        status, score, msg = "red", 10.0, f"Critical — balance covers less than 1 month of fixed costs."

    return RuleResult(
        "emergency_fund", "Emergency Fund", status, round(score, 1), msg, priority=2,
        details={"current_balance": round(current_balance, 2), "avg_monthly_fixed": round(avg_fixed, 2), "months_covered": round(months_covered, 2)},
    )


def rule_subscription_detector(monthly: dict[str, list[dict]]) -> RuleResult:
    """Subscription detector: recurring charges should not exceed 15% of income."""
    TARGET_RATIO = 0.15
    ratios = []
    for txs in monthly.values():
        inc = _income(txs)
        if inc == 0:
            continue
        subs = _cat_expenses(txs, "subscriptions")
        ratios.append(subs / inc)

    if not ratios:
        return RuleResult("subscription_detector", "Subscription Cap", "green", 100, "No data.", priority=4)

    avg_ratio = statistics.mean(ratios)

    if avg_ratio <= TARGET_RATIO:
        status = "green"
        score = 100.0
        msg = f"Subscriptions are {avg_ratio:.1%} of income (limit 15%)."
    elif avg_ratio <= 0.22:
        status = "amber"
        score = 55.0
        msg = f"Subscriptions are {avg_ratio:.1%} of income — slightly over the 15% limit."
    else:
        status = "red"
        score = 20.0
        msg = f"Subscriptions are {avg_ratio:.1%} of income — well above the 15% limit. Review recurring charges."

    return RuleResult(
        "subscription_detector", "Subscription Cap (15%)", status, round(score, 1), msg, priority=4,
        details={"avg_ratio": round(avg_ratio, 4), "target": TARGET_RATIO},
    )


def rule_leisure_cap(monthly: dict[str, list[dict]]) -> RuleResult:
    """Leisure cap: restaurants + entertainment + leisure ≤ 20% of income."""
    TARGET_RATIO = 0.20
    LEISURE_CATS = {"restaurants", "entertainment"}
    ratios = []
    for txs in monthly.values():
        inc = _income(txs)
        if inc == 0:
            continue
        leisure = _cat_expenses(txs, *LEISURE_CATS)
        ratios.append(leisure / inc)

    if not ratios:
        return RuleResult("leisure_cap", "Leisure Cap", "green", 100, "No data.", priority=5)

    avg_ratio = statistics.mean(ratios)
    if avg_ratio <= TARGET_RATIO:
        status, score, msg = "green", 100.0, f"Leisure spending is {avg_ratio:.1%} of income (limit 20%)."
    elif avg_ratio <= 0.30:
        status, score, msg = "amber", 55.0, f"Leisure spending is {avg_ratio:.1%} of income — slightly above 20%."
    else:
        status, score, msg = "red", 20.0, f"Leisure spending is {avg_ratio:.1%} of income — significantly above 20%."

    return RuleResult(
        "leisure_cap", "Leisure Cap (20%)", status, round(score, 1), msg, priority=5,
        details={"avg_ratio": round(avg_ratio, 4), "target": TARGET_RATIO},
    )


def rule_outlier_detector(monthly: dict[str, list[dict]]) -> RuleResult:
    """Outlier detector: flags any transaction > 2× the 3-month category average."""
    # Build 3-month rolling averages per category
    all_months = sorted(monthly.keys())
    outliers = []

    for i, month in enumerate(all_months):
        # Use up to 3 prior months for baseline
        prior_months = all_months[max(0, i - 3):i]
        if not prior_months:
            continue

        cat_totals: dict[str, list[float]] = defaultdict(list)
        for pm in prior_months:
            for tx in monthly[pm]:
                if tx["amount"] < 0 and tx.get("category") and not tx.get("is_reversal"):
                    cat_totals[tx["category"]].append(abs(tx["amount"]))

        cat_avg = {cat: statistics.mean(vals) for cat, vals in cat_totals.items() if vals}

        for tx in monthly[month]:
            cat = tx.get("category")
            if not cat or tx["amount"] >= 0 or tx.get("is_reversal"):
                continue
            avg = cat_avg.get(cat)
            if avg and abs(tx["amount"]) > 2 * avg:
                outliers.append({
                    "month": month,
                    "date": tx["date"],
                    "description": tx["description"][:80],
                    "amount": tx["amount"],
                    "category": cat,
                    "category_avg": round(avg, 2),
                    "ratio": round(abs(tx["amount"]) / avg, 1),
                })

    if not outliers:
        status, score, msg = "green", 100.0, "No spending outliers detected."
    elif len(outliers) <= 2:
        status, score, msg = "amber", 65.0, f"{len(outliers)} unusual transaction(s) detected (>2× category average)."
    else:
        status, score, msg = "red", 30.0, f"{len(outliers)} unusual transactions detected. Review spending spikes."

    return RuleResult(
        "outlier_detector", "Spending Outliers", status, round(score, 1), msg, priority=3,
        details={"outlier_count": len(outliers), "outliers": outliers[:10]},
    )


def rule_503020(monthly: dict[str, list[dict]]) -> RuleResult:
    """50/30/20 rule: needs≤50%, wants≤30%, savings≥20%."""
    NEEDS_CATS = {"housing", "groceries", "health", "transport", "admin"}
    WANTS_CATS = {"restaurants", "entertainment", "shopping", "subscriptions"}

    needs_ratios, wants_ratios, savings_ratios = [], [], []

    for txs in monthly.values():
        inc = _income(txs)
        if inc == 0:
            continue
        needs = _cat_expenses(txs, *NEEDS_CATS) / inc
        wants = _cat_expenses(txs, *WANTS_CATS) / inc
        savings = max(0, (inc - _expenses(txs)) / inc)
        needs_ratios.append(needs)
        wants_ratios.append(wants)
        savings_ratios.append(savings)

    if not needs_ratios:
        return RuleResult("rule_503020", "50/30/20 Rule", "amber", 50, "Not enough data.", priority=6)

    avg_needs = statistics.mean(needs_ratios)
    avg_wants = statistics.mean(wants_ratios)
    avg_savings = statistics.mean(savings_ratios)

    violations = []
    if avg_needs > 0.50:
        violations.append(f"Needs {avg_needs:.0%} > 50%")
    if avg_wants > 0.30:
        violations.append(f"Wants {avg_wants:.0%} > 30%")
    if avg_savings < 0.20:
        violations.append(f"Savings {avg_savings:.0%} < 20%")

    if not violations:
        status, score, msg = "green", 100.0, f"50/30/20 rule met: needs {avg_needs:.0%}, wants {avg_wants:.0%}, savings {avg_savings:.0%}."
    elif len(violations) == 1:
        status, score, msg = "amber", 60.0, f"Minor imbalance: {violations[0]}."
    else:
        status, score, msg = "red", 25.0, f"Multiple violations: {'; '.join(violations)}."

    return RuleResult(
        "rule_503020", "50/30/20 Rule", status, round(score, 1), msg, priority=6,
        details={"avg_needs": round(avg_needs, 4), "avg_wants": round(avg_wants, 4), "avg_savings": round(avg_savings, 4)},
    )


def rule_lifestyle_inflation(monthly: dict[str, list[dict]]) -> RuleResult:
    """Lifestyle inflation: alert if avg monthly spend grew >5% vs prior 3 months without income increase."""
    all_months = sorted(monthly.keys())
    if len(all_months) < 4:
        return RuleResult("lifestyle_inflation", "Lifestyle Inflation", "green", 80,
                          "Not enough months to assess lifestyle inflation (need ≥4).", priority=7)

    # Split into prior half and recent half
    mid = len(all_months) // 2
    prior_months = all_months[:mid]
    recent_months = all_months[mid:]

    def avg_expense(months: list[str]) -> float:
        vals = [_expenses(monthly[m]) for m in months]
        return statistics.mean(vals) if vals else 0

    def avg_income(months: list[str]) -> float:
        vals = [_income(monthly[m]) for m in months if _income(monthly[m]) > 0]
        return statistics.mean(vals) if vals else 0

    prior_exp = avg_expense(prior_months)
    recent_exp = avg_expense(recent_months)
    prior_inc = avg_income(prior_months)
    recent_inc = avg_income(recent_months)

    if prior_exp == 0:
        return RuleResult("lifestyle_inflation", "Lifestyle Inflation", "green", 80, "Not enough data.", priority=7)

    exp_growth = (recent_exp - prior_exp) / prior_exp
    inc_growth = (recent_inc - prior_inc) / prior_inc if prior_inc > 0 else 0

    if exp_growth <= 0.05:
        status, score = "green", 100.0
        msg = f"Spending stable: {exp_growth:+.1%} change vs prior period."
    elif exp_growth <= 0.10 or inc_growth >= exp_growth * 0.8:
        status, score = "amber", 55.0
        msg = f"Mild inflation: spending +{exp_growth:.1%}, income {inc_growth:+.1%}."
    else:
        status, score = "red", 20.0
        msg = f"Lifestyle inflation detected: spending +{exp_growth:.1%} without matching income growth ({inc_growth:+.1%})."

    return RuleResult(
        "lifestyle_inflation", "Lifestyle Inflation", status, round(score, 1), msg, priority=7,
        details={
            "prior_avg_expense": round(prior_exp, 2),
            "recent_avg_expense": round(recent_exp, 2),
            "expense_growth": round(exp_growth, 4),
            "income_growth": round(inc_growth, 4),
        },
    )


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class HealthEngine:
    def __init__(self, current_balance: float | None = None):
        self._balance = current_balance

    def analyze(self, transactions: list[dict]) -> HealthReport:
        # Filter reversals for most rules
        clean_txs = [t for t in transactions if not t.get("is_reversal")]
        monthly = _group_by_month(clean_txs)

        results = [
            rule_savings_rate(monthly),
            rule_emergency_fund(monthly, self._balance),
            rule_subscription_detector(monthly),
            rule_leisure_cap(monthly),
            rule_outlier_detector(monthly),
            rule_503020(monthly),
            rule_lifestyle_inflation(monthly),
        ]

        # Weighted average score (all equal weight)
        overall = round(statistics.mean(r.score for r in results), 1)

        alerts = sorted(
            [r for r in results if r.status in ("amber", "red")],
            key=lambda r: (0 if r.status == "red" else 1, r.priority),
        )

        total_income = sum(_income(txs) for txs in monthly.values())
        total_expenses = sum(_expenses(txs) for txs in monthly.values())

        return HealthReport(
            overall_score=overall,
            grade=_grade(overall),
            rules=results,
            alerts=alerts,
            months_analyzed=sorted(monthly.keys()),
            summary={
                "total_income": round(total_income, 2),
                "total_expenses": round(total_expenses, 2),
                "net_savings": round(total_income - total_expenses, 2),
                "months_analyzed": len(monthly),
                "transaction_count": len(clean_txs),
            },
        )
