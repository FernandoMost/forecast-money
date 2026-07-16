/**
 * lib/translateRule.ts
 *
 * Translates RuleResult name + message using the frontend translation system.
 * The backend sends rule_id, status, and details — we rebuild the human-readable
 * strings here so they respect the user's selected language.
 */

import type { RuleResult } from "@/lib/api";

type TFn = (key: string, vars?: Record<string, string | number>) => string;

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function signedPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

export function translateRuleName(ruleId: string, t: TFn): string {
  const key = `rules.${ruleId}.name`;
  const result = t(key);
  // If key not found, t() returns the key itself — fall back to ruleId
  return result === key ? ruleId : result;
}

export function translateRuleMessage(rule: RuleResult, t: TFn): string {
  const d = rule.details as Record<string, unknown>;
  const id = rule.rule_id;
  const status = rule.status;

  switch (id) {
    case "savings_rate": {
      if (!d || d.avg_rate === undefined) return t(`rules.${id}.noData`);
      const rate = pct(d.avg_rate as number);
      const months = d.months_analyzed as number;
      const on = d.months_on_target as number;
      const total = months;
      if (status === "green") return t(`rules.${id}.green`, { rate, months });
      if (status === "amber") return t(`rules.${id}.amber`, { rate, on, total });
      return t(`rules.${id}.red`, { rate, on, total });
    }

    case "emergency_fund": {
      if (!d || d.current_balance === undefined) return t(`rules.${id}.unknown`);
      if (d.avg_monthly_fixed === undefined) return t(`rules.${id}.noFixed`);
      const months = (d.months_covered as number).toFixed(1);
      if (status === "green" && (d.months_covered as number) >= 6) return t(`rules.${id}.excellent`, { months });
      if (status === "green") return t(`rules.${id}.good`, { months });
      if (status === "amber") {
        // could be "no fixed data" case
        if ((d.months_covered as number) < 1) return t(`rules.${id}.critical`);
        return t(`rules.${id}.low`, { months });
      }
      if ((d.months_covered as number) < 1) return t(`rules.${id}.critical`);
      return t(`rules.${id}.low`, { months });
    }

    case "subscription_detector": {
      if (!d || d.avg_ratio === undefined) return t(`rules.${id}.noData`);
      const rate = pct(d.avg_ratio as number);
      return t(`rules.${id}.${status}`, { rate });
    }

    case "leisure_cap": {
      if (!d || d.avg_ratio === undefined) return t(`rules.${id}.noData`);
      const rate = pct(d.avg_ratio as number);
      return t(`rules.${id}.${status}`, { rate });
    }

    case "outlier_detector": {
      if (!d) return t(`rules.${id}.green`);
      if (status === "green") return t(`rules.${id}.green`);
      const count = (d.outlier_count as number) ?? 0;
      return t(`rules.${id}.${status}`, { count });
    }

    case "rule_503020": {
      if (!d || d.avg_needs === undefined) return t(`rules.${id}.noData`);
      const needs = pct(d.avg_needs as number);
      const wants = pct(d.avg_wants as number);
      const savings = pct(d.avg_savings as number);

      if (status === "green") return t(`rules.${id}.green`, { needs, wants, savings });

      // Rebuild violations in the target language
      const violations: string[] = [];
      if ((d.avg_needs as number) > 0.50) violations.push(t("rules.rule_503020.violation_needs", { pct: pct(d.avg_needs as number) }));
      if ((d.avg_wants as number) > 0.30) violations.push(t("rules.rule_503020.violation_wants", { pct: pct(d.avg_wants as number) }));
      if ((d.avg_savings as number) < 0.20) violations.push(t("rules.rule_503020.violation_savings", { pct: pct(d.avg_savings as number) }));

      if (status === "amber" && violations.length > 0)
        return t(`rules.${id}.amber`, { violation: violations[0] });
      return t(`rules.${id}.red`, { violations: violations.join("; ") });
    }

    case "lifestyle_inflation": {
      if (!d) return t(`rules.${id}.noData`);
      if (d.prior_avg_expense === undefined) return t(`rules.${id}.green_nodata`);
      const exp_change = signedPct(d.expense_growth as number);
      const inc_change = signedPct(d.income_growth as number);
      if (status === "green") {
        if ((d.expense_growth as number) <= 0.05)
          return t(`rules.${id}.green_stable`, { change: exp_change });
        return t(`rules.${id}.green_nodata`);
      }
      if (status === "amber") return t(`rules.${id}.amber`, { exp_change, inc_change });
      return t(`rules.${id}.red`, { exp_change, inc_change });
    }

    default:
      // Unknown rule — return original backend message
      return rule.message;
  }
}
