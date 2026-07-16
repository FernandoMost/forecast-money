"use client";

import { useEffect, useRef, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import { api, HealthScore, HealthScoreHistoryEntry, RuleResult } from "@/lib/api";
import { formatEur, STATUS_COLORS, STATUS_BADGE } from "@/lib/utils";
import { useT } from "@/lib/i18n";
import { translateRuleName, translateRuleMessage } from "@/lib/translateRule";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RULE_ORDER = [
  "savings_rate", "emergency_fund", "subscription_detector",
  "leisure_cap", "outlier_detector", "rule_503020", "lifestyle_inflation",
];

function statusIcon(s: string) {
  return s === "green" ? "✓" : s === "amber" ? "!" : "✗";
}

function pct(v: number) { return `${(v * 100).toFixed(1)}%`; }
function pctOf(v: number) { return `${v.toFixed(1)}%`; }

// ---------------------------------------------------------------------------
// Score gauge — circular SVG arc
// ---------------------------------------------------------------------------

function ScoreGauge({ score, grade }: { score: number; grade: string }) {
  const { t } = useT();
  const color = score >= 80 ? "#16a34a" : score >= 55 ? "#d97706" : "#dc2626";
  const r = 52;
  const circ = 2 * Math.PI * r;
  const arc = circ * 0.75; // 270° arc
  const filled = arc * (score / 100);
  const offset = circ * 0.125; // start at 225°

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={140} height={120} viewBox="0 0 140 120">
        {/* Track */}
        <circle
          cx={70} cy={75} r={r}
          fill="none" stroke="#e5e7eb" strokeWidth={10}
          strokeDasharray={`${arc} ${circ - arc}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(135 70 75)"
        />
        {/* Fill */}
        <circle
          cx={70} cy={75} r={r}
          fill="none" stroke={color} strokeWidth={10}
          strokeDasharray={`${filled} ${circ - filled}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(135 70 75)"
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
        <text x={70} y={72} textAnchor="middle" fontSize={26} fontWeight={800} fill={color}>{score}</text>
        <text x={70} y={90} textAnchor="middle" fontSize={13} fill="#6b7280">{t("health.grade", { grade })}</text>
      </svg>
      <span className="text-xs text-gray-400 dark:text-gray-500">{t("health.score")}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// History sparkline for overall score
// ---------------------------------------------------------------------------

function HistoryChart({ history }: { history: HealthScoreHistoryEntry[] }) {
  const { t } = useT();
  if (history.length < 2) {
    return (
      <div className="text-xs text-gray-400 dark:text-gray-500 italic py-4 text-center">
        {t("health.historyEmpty")}
      </div>
    );
  }

  const data = [...history].reverse().map((h) => ({
    date: h.recorded_at.slice(0, 10),
    score: h.overall_score,
    grade: h.grade,
  }));

  return (
    <ResponsiveContainer width="100%" height={120}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickLine={false} />
        <Tooltip
          formatter={(v: unknown) => [`${(v as number).toFixed(1)}`, t("health.scoreLabel")]}
          labelStyle={{ fontSize: 11 }}
          contentStyle={{ fontSize: 11 }}
        />
        <ReferenceLine y={85} stroke="#16a34a" strokeDasharray="4 2" strokeOpacity={0.4} />
        <ReferenceLine y={55} stroke="#d97706" strokeDasharray="4 2" strokeOpacity={0.4} />
        <Area
          type="monotone" dataKey="score"
          stroke="#6366f1" strokeWidth={2}
          fill="url(#scoreGrad)" dot={{ r: 3, fill: "#6366f1" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Rule card wrapper
// ---------------------------------------------------------------------------

function RuleSection({
  rule,
  children,
}: {
  rule: RuleResult;
  children: React.ReactNode;
}) {
  const { t } = useT();
  const border =
    rule.status === "green" ? "border-green-200" :
    rule.status === "amber" ? "border-amber-200" : "border-red-200";
  const bg =
    rule.status === "green" ? "bg-green-50 dark:bg-green-950/30" :
    rule.status === "amber" ? "bg-amber-50 dark:bg-amber-950/30" : "bg-red-50 dark:bg-red-950/30";

  return (
    <section id={rule.rule_id} className={`rounded-2xl border ${border} overflow-hidden scroll-mt-20`}>
      {/* Header */}
      <div className={`${bg} px-5 py-4 flex items-start justify-between gap-4`}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${STATUS_BADGE[rule.status]}`}>
              {statusIcon(rule.status)} {rule.status.toUpperCase()}
            </span>
            <h2 className="font-bold text-gray-900 dark:text-white text-base">{translateRuleName(rule.rule_id, t)}</h2>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{translateRuleMessage(rule, t)}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-2xl font-black text-gray-800 dark:text-gray-200">{rule.score.toFixed(0)}</div>
          <div className="text-xs text-gray-400 dark:text-gray-500">{t("health.outOf100")}</div>
        </div>
      </div>
      {/* Body */}
      <div className="bg-white dark:bg-gray-900 px-5 py-4 space-y-4">
        {children}
      </div>
    </section>
  );
}

// Helper: small stat chip
function Stat({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`rounded-lg px-3 py-2 text-center ${highlight ? "bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-100" : "bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-800"}`}>
      <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{label}</div>
      <div className={`font-bold text-sm mt-0.5 ${highlight ? "text-indigo-700" : "text-gray-800 dark:text-gray-200"}`}>{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rule detail renderers
// ---------------------------------------------------------------------------

// 3.1 Savings rate
function SavingsRateDetail({ d }: { d: Record<string, unknown> }) {
  const { t } = useT();
  const mb = (d.monthly_breakdown as Array<{
    month: string; income: number; expenses: number; savings: number; rate: number; on_target: boolean;
  }>) ?? [];

  return (
    <>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <Stat label={t("health.savingsAvg")} value={pct(d.avg_rate as number)} highlight />
        <Stat label={t("health.savingsTarget")} value={pct(d.target as number)} />
        <Stat label={t("health.savingsOnTarget")} value={`${d.months_on_target}/${d.months_analyzed}`} />
      </div>
      {mb.length > 0 && (
        <>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{t("health.savingsChart")}</p>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={mb} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} tickLine={false} />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} domain={[-0.1, 0.4]} />
              <Tooltip formatter={(v: unknown) => [`${((v as number) * 100).toFixed(1)}%`, "Savings rate"]} labelStyle={{ fontSize: 11 }} contentStyle={{ fontSize: 11 }} />
              <ReferenceLine y={0.10} stroke="#6366f1" strokeDasharray="4 2" label={{ value: "10% target", fontSize: 10, fill: "#6366f1", position: "insideRight" }} />
              {mb.map((entry) => (
                <Cell key={entry.month} fill={entry.on_target ? "#16a34a" : "#dc2626"} />
              ))}
              <Bar dataKey="rate" radius={[3, 3, 0, 0]}>
                {mb.map((entry, i) => <Cell key={i} fill={entry.on_target ? "#16a34a" : "#ef4444"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-800">
                <th className="py-1 text-left font-medium">{t("health.savingsCol.month")}</th>
                <th className="py-1 text-right font-medium">{t("health.savingsCol.income")}</th>
                <th className="py-1 text-right font-medium">{t("health.savingsCol.expenses")}</th>
                <th className="py-1 text-right font-medium">{t("health.savingsCol.savings")}</th>
                <th className="py-1 text-right font-medium">{t("health.savingsCol.rate")}</th>
              </tr></thead>
              <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                {mb.map((r) => (
                  <tr key={r.month} className={r.on_target ? "text-green-700" : "text-red-600"}>
                    <td className="py-1">{r.month}</td>
                    <td className="py-1 text-right tabular-nums">{formatEur(r.income)}</td>
                    <td className="py-1 text-right tabular-nums">{formatEur(r.expenses)}</td>
                    <td className="py-1 text-right tabular-nums font-semibold">{formatEur(r.savings)}</td>
                    <td className="py-1 text-right tabular-nums font-semibold">{pct(r.rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

// 3.2 Emergency fund
function EmergencyFundDetail({ d }: { d: Record<string, unknown> }) {
  const { t } = useT();
  const bycat = (d.fixed_by_category as Array<{ category: string; avg_monthly: number; total: number; tx_count: number }>) ?? [];

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
        <Stat label={t("health.emergencyBalance")} value={formatEur(d.current_balance as number)} highlight />
        <Stat label={t("health.emergencyFixed")} value={formatEur(d.avg_monthly_fixed as number)} />
        <Stat label={t("health.emergencyMonths")} value={`${(d.months_covered as number).toFixed(1)} mo`} />
        <Stat label={t("health.emergencyTarget")} value={t("health.emergencyRange")} />
      </div>

      {/* Progress bar: balance vs 3-month and 6-month targets */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-gray-400 dark:text-gray-500">
          <span>€0</span>
          <span className="text-amber-600">3 mo: {formatEur(d.balance_for_3_months as number)}</span>
          <span className="text-green-600">6 mo: {formatEur(d.balance_for_6_months as number)}</span>
        </div>
        <div className="relative h-3 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
          {/* 6-month target bar */}
          <div className="absolute inset-y-0 left-0 bg-green-200 rounded-full"
            style={{ width: "100%" }} />
          {/* 3-month marker */}
          <div className="absolute inset-y-0 left-1/2 w-0.5 bg-amber-400" />
          {/* Current balance */}
          <div
            className="absolute inset-y-0 left-0 bg-indigo-500 rounded-full transition-all"
            style={{
              width: `${Math.min(100, ((d.current_balance as number) / (d.balance_for_6_months as number)) * 100)}%`
            }}
          />
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500 text-center">
          {t("health.emergencyCaption", { months: (d.months_covered as number).toFixed(1) })}
        </p>
      </div>

      {bycat.length > 0 && (
        <>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{t("health.emergencyBreakdown")}</p>
          <div className="space-y-1">
            {bycat.map((c) => (
              <div key={c.category} className="flex items-center gap-2 text-sm">
                <span className="w-28 capitalize text-gray-600 dark:text-gray-400 truncate">{c.category}</span>
                <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-400 rounded-full"
                    style={{ width: `${Math.min(100, (c.avg_monthly / (d.avg_monthly_fixed as number)) * 100)}%` }}
                  />
                </div>
                <span className="text-gray-700 dark:text-gray-300 font-medium tabular-nums w-20 text-right">{formatEur(c.avg_monthly)}/mo</span>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

// 3.3 Subscription cap
function SubscriptionDetail({ d }: { d: Record<string, unknown> }) {
  const { t } = useT();
  const subs = (d.top_subscriptions as Array<{ label: string; total: number; avg_monthly: number }>) ?? [];

  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        <Stat label={t("health.subsAvg")} value={pct(d.avg_ratio as number)} highlight />
        <Stat label={t("health.subsLimit")} value={pct(d.target as number)} />
        <Stat label={t("health.subsMonthly")} value={formatEur(d.avg_monthly_subscriptions as number)} />
      </div>
      {subs.length > 0 && (
        <>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{t("health.subsList")}</p>
          <div className="space-y-1">
            {subs.map((s) => (
              <div key={s.label} className="flex items-center justify-between text-sm py-1 border-b border-gray-50 dark:border-gray-800 last:border-0">
                <span className="text-gray-700 dark:text-gray-300 truncate flex-1 mr-4">{s.label}</span>
                <span className="text-gray-500 dark:text-gray-400 text-xs mr-3">{formatEur(s.avg_monthly)}/mo</span>
                <span className="font-medium tabular-nums text-gray-800 dark:text-gray-200">{formatEur(s.total)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

// 3.4 Leisure cap
function LeisureCapDetail({ d }: { d: Record<string, unknown> }) {
  const { t } = useT();
  const txs = (d.latest_transactions as Array<{ date: string; description: string; category: string; subcategory: string | null; amount: number }>) ?? [];
  const spent = d.latest_leisure_spent as number;
  const budget = d.latest_leisure_budget as number;
  const remaining = d.latest_leisure_remaining as number;
  const pctUsed = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Stat label={t("health.leisureAvg")} value={pct(d.avg_ratio as number)} highlight />
        <Stat label={t("health.leisureLimit")} value={pct(d.target as number)} />
        <Stat label={t("health.leisureSpent", { month: d.latest_month as string })} value={formatEur(spent)} />
        <Stat label={t("health.leisureBudget")} value={formatEur(budget)} />
      </div>

      {/* Budget progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>{formatEur(spent)} spent</span>
          <span className={remaining >= 0 ? "text-green-600" : "text-red-600"}>
            {remaining >= 0
              ? t("health.leisureLeft", { amount: formatEur(remaining) })
              : t("health.leisureOver", { amount: formatEur(Math.abs(remaining)) })}
          </span>
        </div>
        <div className="h-3 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${remaining >= 0 ? "bg-orange-400" : "bg-red-500"}`}
            style={{ width: `${pctUsed}%` }}
          />
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500 text-center">
          {t("health.leisureCaption", {
            budget: formatEur(budget),
            income: formatEur(d.latest_income as number),
            month: d.latest_month as string,
          })}
        </p>
      </div>

      {txs.length > 0 && (
        <>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{t("health.leisureTxs", { month: d.latest_month as string })}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-800">
                <th className="py-1 text-left font-medium">{t("health.leisureCols.date")}</th>
                <th className="py-1 text-left font-medium">{t("health.leisureCols.desc")}</th>
                <th className="py-1 text-left font-medium">{t("health.leisureCols.cat")}</th>
                <th className="py-1 text-right font-medium">{t("health.leisureCols.amount")}</th>
              </tr></thead>
              <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                {txs.map((tx, i) => (
                  <tr key={i}>
                    <td className="py-1 text-gray-400 dark:text-gray-500 whitespace-nowrap">{tx.date}</td>
                    <td className="py-1 text-gray-700 dark:text-gray-300 max-w-[180px] truncate">{tx.description}</td>
                    <td className="py-1 text-gray-500 dark:text-gray-400">{tx.subcategory ?? tx.category}</td>
                    <td className="py-1 text-right tabular-nums font-medium text-gray-800 dark:text-gray-200">{formatEur(tx.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

// 3.5 Spending outliers
function OutliersDetail({ d }: { d: Record<string, unknown> }) {
  const { t } = useT();
  const outliers = (d.outliers as Array<{
    month: string; date: string; description: string; amount: number;
    category: string; subcategory?: string; category_avg: number; ratio: number;
  }>) ?? [];

  if (outliers.length === 0) {
    return <p className="text-sm text-green-700 font-medium">{t("health.outliersNone")}</p>;
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-2">
        <Stat label={t("health.outliersFound")} value={String(d.outlier_count)} highlight />
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">
        {t("health.outliersTxs")}
      </p>
      <div className="space-y-2">
        {outliers.map((o, i) => {
          const severityColor = o.ratio >= 5 ? "border-red-200 bg-red-50 dark:bg-red-950/30" : o.ratio >= 3 ? "border-amber-200 bg-amber-50 dark:bg-amber-950/30" : "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50";
          return (
            <div key={i} className={`rounded-lg border px-3 py-2 text-xs ${severityColor}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <span className="font-medium text-gray-800 dark:text-gray-200 block truncate">{o.description}</span>
                  <span className="text-gray-500 dark:text-gray-400">{o.date} · {o.subcategory ?? o.category}</span>
                </div>
                <div className="shrink-0 text-right">
                  <div className="font-bold text-gray-800 dark:text-gray-200 tabular-nums">{formatEur(o.amount)}</div>
                  <div className="text-gray-500 dark:text-gray-400">{o.ratio}× avg ({formatEur(o.category_avg)})</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

// 3.6 50/30/20
function Rule503020Detail({ d }: { d: Record<string, unknown> }) {
  const { t } = useT();
  const mb = (d.monthly_breakdown as Array<{
    month: string; income: number; needs: number; wants: number; savings: number;
    needs_pct: number; wants_pct: number; savings_pct: number;
  }>) ?? [];
  const needsByCat = (d.needs_by_category as Array<{ category: string; avg_monthly: number; total: number }>) ?? [];
  const wantsByCat = (d.wants_by_category as Array<{ category: string; avg_monthly: number; total: number }>) ?? [];
  const violations = (d.violations as string[]) ?? [];

  const avgNeeds = (d.avg_needs as number) * 100;
  const avgWants = (d.avg_wants as number) * 100;
  const avgSavings = (d.avg_savings as number) * 100;

  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: t("health.needs"), val: avgNeeds, target: 50, ok: avgNeeds <= 50 },
          { label: t("health.wants"), val: avgWants, target: 30, ok: avgWants <= 30 },
          { label: t("health.savingsRule"), val: avgSavings, target: 20, ok: avgSavings >= 20 },
        ].map(({ label, val, target, ok }) => (
          <div key={label} className={`rounded-lg px-3 py-2 border text-center ${ok ? "bg-green-50 dark:bg-green-950/30 border-green-200" : "bg-red-50 dark:bg-red-950/30 border-red-200"}`}>
            <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{label}</div>
            <div className={`font-bold text-sm mt-0.5 ${ok ? "text-green-700" : "text-red-600"}`}>{pctOf(val)}</div>
          </div>
        ))}
      </div>

      {violations.length > 0 && (
        <div className="space-y-1">
          {violations.map((v, i) => (
            <div key={i} className="text-xs text-red-700 bg-red-50 dark:bg-red-950/30 border border-red-100 rounded px-3 py-1.5">
              ✗ {v}
            </div>
          ))}
        </div>
      )}

      {mb.length > 0 && (
        <>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{t("health.monthlyBreakdown")}</p>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={mb} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} tickLine={false} />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
              <Tooltip
                formatter={(v: unknown) => [`${(v as number).toFixed(1)}%`]}
                labelStyle={{ fontSize: 11 }}
                contentStyle={{ fontSize: 11 }}
              />
              <ReferenceLine y={50} stroke="#6366f1" strokeDasharray="4 2" strokeOpacity={0.5} />
              <ReferenceLine y={30} stroke="#f97316" strokeDasharray="4 2" strokeOpacity={0.5} />
              <Bar dataKey="needs_pct" name="Needs" stackId="a" fill="#6366f1" radius={[0, 0, 0, 0]} />
              <Bar dataKey="wants_pct" name="Wants" stackId="a" fill="#f97316" />
              <Bar dataKey="savings_pct" name="Savings" stackId="a" fill="#22c55e" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}

      <div className="grid grid-cols-2 gap-4">
        {needsByCat.length > 0 && (
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide mb-1">{t("health.needsCats")}</p>
            {needsByCat.map((c) => (
              <div key={c.category} className="flex justify-between text-xs py-0.5 border-b border-gray-50 dark:border-gray-800">
                <span className="text-gray-600 dark:text-gray-400 capitalize">{c.category}</span>
                <span className="font-medium text-gray-800 dark:text-gray-200 tabular-nums">{formatEur(c.avg_monthly)}/mo</span>
              </div>
            ))}
          </div>
        )}
        {wantsByCat.length > 0 && (
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide mb-1">{t("health.wantsCats")}</p>
            {wantsByCat.map((c) => (
              <div key={c.category} className="flex justify-between text-xs py-0.5 border-b border-gray-50 dark:border-gray-800">
                <span className="text-gray-600 dark:text-gray-400 capitalize">{c.category}</span>
                <span className="font-medium text-gray-800 dark:text-gray-200 tabular-nums">{formatEur(c.avg_monthly)}/mo</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

// 3.7 Lifestyle inflation
function LifestyleInflationDetail({ d }: { d: Record<string, unknown> }) {
  const { t } = useT();
  const ts = (d.time_series as Array<{ month: string; income: number; expenses: number; in_prior_period: boolean }>) ?? [];

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Stat label={t("health.inflationPrior")} value={formatEur(d.prior_avg_expense as number)} />
        <Stat label={t("health.inflationRecent")} value={formatEur(d.recent_avg_expense as number)} highlight />
        <Stat label={t("health.inflationExpense")} value={`${((d.expense_growth as number) * 100).toFixed(1)}%`} />
        <Stat label={t("health.inflationIncome")} value={`${((d.income_growth as number) * 100).toFixed(1)}%`} />
      </div>

      {ts.length >= 2 && (
        <>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{t("health.inflationChart")}</p>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={ts} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} tickLine={false} />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} tickFormatter={(v) => `€${(v / 1000).toFixed(0)}k`} />
              <Tooltip formatter={(v: unknown) => [formatEur(v as number)]} labelStyle={{ fontSize: 11 }} contentStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="income" name={t("health.inflationIncomeLegend")} stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="expenses" name={t("health.inflationExpenseLegend")} stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
          <div className="flex gap-4 text-xs text-gray-500 dark:text-gray-400 justify-center">
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-green-500 inline-block" /> {t("health.inflationIncomeLegend")}</span>
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-indigo-500 inline-block" /> {t("health.inflationExpenseLegend")}</span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-gray-300 inline-block border-dashed border-t border-gray-400" />
              {t("health.inflationDivider")}
            </span>
          </div>
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Rule detail dispatcher
// ---------------------------------------------------------------------------

function RuleDetail({ rule }: { rule: RuleResult }) {
  const d = rule.details as Record<string, unknown>;
  switch (rule.rule_id) {
    case "savings_rate":         return <SavingsRateDetail d={d} />;
    case "emergency_fund":       return <EmergencyFundDetail d={d} />;
    case "subscription_detector": return <SubscriptionDetail d={d} />;
    case "leisure_cap":          return <LeisureCapDetail d={d} />;
    case "outlier_detector":     return <OutliersDetail d={d} />;
    case "rule_503020":          return <Rule503020Detail d={d} />;
    case "lifestyle_inflation":  return <LifestyleInflationDetail d={d} />;
    default: return null;
  }
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function HealthPage() {
  const { t } = useT();
  const [health, setHealth] = useState<HealthScore | null>(null);
  const [history, setHistory] = useState<HealthScoreHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api.healthScore(),
      api.healthHistory(),
    ]).then(([h, hist]) => {
      setHealth(h);
      setHistory(hist.history);
    }).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load health data.");
    }).finally(() => setLoading(false));
  }, []);

  // Scroll to hash on load
  const didScroll = useRef(false);
  useEffect(() => {
    if (!health || didScroll.current) return;
    const hash = window.location.hash.slice(1);
    if (hash) {
      const el = document.getElementById(hash);
      if (el) { el.scrollIntoView({ behavior: "smooth" }); didScroll.current = true; }
    }
  }, [health]);

  if (loading) return <div className="py-24 text-center text-gray-400 dark:text-gray-500">{t("health.loading")}</div>;
  if (error) return <div className="py-24 text-center text-red-500">{error}</div>;
  if (!health) return null;

  // Sort rules: worst first (red → amber → green), then by score asc
  const statusOrder = { red: 0, amber: 1, green: 2 };
  const sortedRules = [...health.rules].sort((a, b) => {
    const sd = (statusOrder[a.status as keyof typeof statusOrder] ?? 2) -
               (statusOrder[b.status as keyof typeof statusOrder] ?? 2);
    return sd !== 0 ? sd : a.score - b.score;
  });

  return (
    <div className="space-y-8 pb-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("health.title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
          {t("health.subtitle")}
        </p>
      </div>

      {/* Score + history */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Gauge */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 flex items-center justify-center">
          <ScoreGauge score={health.overall_score} grade={health.grade} />
        </div>

        {/* History */}
        <div className="md:col-span-2 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
          <h2 className="font-semibold text-gray-700 dark:text-gray-300 text-sm mb-3">{t("health.historyTitle")}</h2>
          <HistoryChart history={history} />
          {history.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {[...history].reverse().slice(-6).map((h) => (
                <div key={h.id} className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                  <span className="text-gray-300 dark:text-gray-600">{h.recorded_at.slice(0, 10)}</span>
                  <span className={`font-bold ${h.overall_score >= 80 ? "text-green-600" : h.overall_score >= 55 ? "text-yellow-600" : "text-red-600"}`}>
                    {h.overall_score.toFixed(0)} ({h.grade})
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label={t("health.statsMonths")} value={String(health.summary.months_analyzed)} />
        <Stat label={t("health.statsTx")} value={health.summary.transaction_count.toLocaleString()} />
        <Stat label={t("health.statsIncome")} value={formatEur(health.summary.total_income)} />
        <Stat label={t("health.statsSavings")} value={formatEur(health.summary.net_savings)} />
      </div>

      {/* Rules sorted worst → best */}
      <div className="space-y-6">
        <h2 className="font-semibold text-gray-700 dark:text-gray-300 text-sm uppercase tracking-wide">
          {t("health.rulesTitle")}
        </h2>
        {sortedRules.map((rule) => (
          <RuleSection key={rule.rule_id} rule={rule}>
            <RuleDetail rule={rule} />
          </RuleSection>
        ))}
      </div>
    </div>
  );
}
