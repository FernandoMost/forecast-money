"use client";

import { useEffect, useState } from "react";
import { api, DashboardData, MonthSummaryForDashboard, RuleResult } from "@/lib/api";
import { formatEur, STATUS_COLORS, STATUS_BADGE, formatDate, toIntlLocale } from "@/lib/utils";
import { useT } from "@/lib/i18n";
import { translateRuleName, translateRuleMessage } from "@/lib/translateRule";
import Link from "next/link";

function StalenessAlert({ days, lastDate }: { days: number; lastDate: string | null }) {
  const { t } = useT();
  if (!lastDate || days < 7) return null;
  const isOld = days >= 30;
  const weeks = Math.floor(days / 7);
  const months = Math.floor(days / 30);
  const label = isOld
    ? t("dashboard.staleMonths", { months })
    : t("dashboard.staleWeeks", { weeks });
  const detail = isOld ? t("dashboard.staleMonthsDetail") : t("dashboard.staleWeeksDetail");
  const styles = isOld ? "bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800 text-red-800 dark:text-red-300"
                       : "bg-yellow-50 dark:bg-yellow-950 border-yellow-200 dark:border-yellow-800 text-yellow-800 dark:text-yellow-300";
  return (
    <div className={`flex gap-3 items-start p-4 rounded-xl border text-sm ${styles}`}>
      <span className="mt-0.5 shrink-0">{isOld ? "🔴" : "🟡"}</span>
      <div><span className="font-semibold">{label}</span><span className="opacity-80"> — {detail}</span></div>
    </div>
  );
}

function ScoreDial({ score, grade }: { score: number; grade: string }) {
  const { t } = useT();
  const color = score >= 80 ? "text-green-600" : score >= 55 ? "text-yellow-600" : "text-red-600";
  return (
    <Link href="/health"
      className="flex flex-col items-center justify-center p-8 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm h-full hover:border-indigo-300 dark:hover:border-indigo-600 transition-colors group"
      title={t("dashboard.viewDetails")}
    >
      <div className={`text-7xl font-black tabular-nums ${color}`}>{score}</div>
      <div className="text-gray-400 dark:text-gray-500 text-sm mt-1">{t("dashboard.outOf100")}</div>
      <div className={`mt-3 text-4xl font-bold ${color}`}>Grade {grade}</div>
      <div className="text-gray-500 dark:text-gray-400 text-sm mt-2">{t("dashboard.financialHealth")}</div>
      <div className="text-xs text-indigo-400 mt-2 group-hover:underline">{t("dashboard.viewDetails")}</div>
    </Link>
  );
}

function MetricCard({ label, value, sub, highlight, tone }: {
  label: string; value: string; sub?: string; highlight?: boolean;
  tone?: "positive" | "negative" | "neutral";
}) {
  const valueColor = tone === "positive" ? "text-green-700 dark:text-green-400"
    : tone === "negative" ? "text-red-600 dark:text-red-400" : "text-gray-900 dark:text-white";
  return (
    <div className={`rounded-xl border p-5 shadow-sm ${
      highlight ? "bg-indigo-50 dark:bg-indigo-950 border-indigo-200 dark:border-indigo-700"
                : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700"
    }`}>
      <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${valueColor}`}>{value}</div>
      {sub && <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function PrimaryMonthCards({ m, isCurrentMonth }: { m: MonthSummaryForDashboard; isCurrentMonth: boolean }) {
  const { t } = useT();
  const leisureTone: "positive" | "negative" | "neutral" = m.leisure_remaining > 0 ? "positive" : "negative";
  const savingsTone: "positive" | "negative" | "neutral" = m.net_savings > 0 ? "positive" : "negative";
  const showPace = isCurrentMonth && m.days_elapsed != null && m.days_in_month != null && m.projected_month_end_expenses != null;
  const paceTone: "positive" | "negative" | "neutral" =
    m.projected_month_end_expenses != null && m.total_income > 0
      ? m.projected_month_end_expenses < m.total_income ? "positive" : "negative"
      : "neutral";
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
      <MetricCard label={isCurrentMonth ? t("dashboard.labelIncomeCurrent") : t("dashboard.labelIncome")} value={formatEur(m.total_income)} tone="positive" />
      <MetricCard label={isCurrentMonth ? t("dashboard.labelExpensesCurrent") : t("dashboard.labelExpenses")} value={formatEur(m.total_expenses)} tone="negative" />
      <MetricCard label={isCurrentMonth ? t("dashboard.labelNetCurrent") : t("dashboard.labelNet")} value={formatEur(m.net_savings)} sub={m.drew_from_savings ? t("dashboard.drewFromSavings") : undefined} tone={savingsTone} />
      <MetricCard label={t("dashboard.labelLeisure")} value={formatEur(m.leisure_remaining)} sub={t("dashboard.labelLeisureSub", { spent: formatEur(m.leisure_spent), budget: formatEur(m.leisure_budget) })} tone={leisureTone} />
      {showPace && (
        <MetricCard label={t("dashboard.labelProjection")} value={formatEur(m.projected_month_end_expenses!)} sub={t("dashboard.labelProjectionSub", { elapsed: m.days_elapsed!, total: m.days_in_month!, days: m.days_of_data })} tone={paceTone} />
      )}
    </div>
  );
}

function SecondaryMonthStrip({ m, label }: { m: MonthSummaryForDashboard; label: string }) {
  const { t } = useT();
  return (
    <div className="bg-gray-50 dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-3">
      <div className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-2">{label}</div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="text-gray-500 dark:text-gray-400">{t("dashboard.secondaryIncome")} <span className="font-semibold text-gray-800 dark:text-gray-200">{formatEur(m.total_income)}</span></span>
        <span className="text-gray-500 dark:text-gray-400">{t("dashboard.secondaryExpenses")} <span className="font-semibold text-red-600 dark:text-red-400">{formatEur(m.total_expenses)}</span></span>
        <span className="text-gray-500 dark:text-gray-400">
          {t("dashboard.secondaryNet")} <span className={`font-semibold ${m.net_savings >= 0 ? "text-green-700 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>{formatEur(m.net_savings)}</span>
          {m.drew_from_savings && <span className="ml-1 text-yellow-600">⚠</span>}
        </span>
        <span className="text-gray-500 dark:text-gray-400">
          {t("dashboard.secondaryLeisure")} <span className={`font-semibold ${m.leisure_remaining >= 0 ? "text-green-700 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>{formatEur(m.leisure_remaining)}</span>
        </span>
        {m.days_of_data > 0 && m.days_of_data < 15 && (
          <span className="text-gray-400 italic">{t("dashboard.partialData", { days: m.days_of_data })}</span>
        )}
      </div>
    </div>
  );
}

function AlertBanner({ alerts }: { alerts: RuleResult[] }) {
  const { t } = useT();
  if (!alerts.length) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-700 dark:text-gray-300 text-sm uppercase tracking-wide">{t("dashboard.alertsTitle")}</h3>
        <Link href="/health" className="text-xs text-indigo-500 hover:underline">{t("dashboard.alertsLink")}</Link>
      </div>
      {alerts.map((a) => (
        <Link key={a.rule_id} href={`/health#${a.rule_id}`}
          className={`flex gap-3 p-3 rounded-lg border text-sm hover:opacity-90 transition-opacity ${STATUS_COLORS[a.status]}`}>
          <span>{a.status === "red" ? "🔴" : "🟡"}</span>
          <div><span className="font-semibold">{translateRuleName(a.rule_id, t)}:</span> {translateRuleMessage(a, t)}</div>
        </Link>
      ))}
    </div>
  );
}

function CompactRuleGrid({ rules }: { rules: RuleResult[] }) {
  const { t } = useT();
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-700 dark:text-gray-300 text-sm uppercase tracking-wide">{t("dashboard.rulesTitle")}</h3>
        <Link href="/health" className="text-xs text-indigo-500 hover:underline">{t("dashboard.rulesLink")}</Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {rules.map((rule) => (
          <Link key={rule.rule_id} href={`/health#${rule.rule_id}`}
            className="flex items-center justify-between p-3 rounded-xl border bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:border-indigo-200 dark:hover:border-indigo-600 transition-colors gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold shrink-0 ${STATUS_BADGE[rule.status]}`}>
                  {rule.status === "green" ? "✓" : rule.status === "amber" ? "!" : "✗"}
                </span>
                <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 truncate">{translateRuleName(rule.rule_id, t)}</span>
              </div>
              <p className="text-xs text-gray-400 mt-0.5 truncate">{translateRuleMessage(rule, t)}</p>
            </div>
            <div className="text-lg font-black text-gray-700 dark:text-gray-300 shrink-0 tabular-nums">{rule.score.toFixed(0)}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      <div className="h-8 bg-gray-200 dark:bg-gray-800 rounded w-48" />
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="h-48 bg-gray-200 dark:bg-gray-800 rounded-2xl" />
        <div className="md:col-span-3 grid grid-cols-2 sm:grid-cols-3 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-24 bg-gray-200 dark:bg-gray-800 rounded-xl" />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { t, locale } = useT();
  const intlLocale = toIntlLocale(locale);
  const [data, setData] = useState<DashboardData | null>(null);
  const [recentTxs, setRecentTxs] = useState<Awaited<ReturnType<typeof api.transactions>>["items"]>([]);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    api.dashboard()
      .then((d) => { setData(d); return api.transactions({ limit: 8 }); })
      .then((txData) => { setRecentTxs(txData.items); })
      .catch((err) => { if (err?.name !== "AuthError") setEmpty(true); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Skeleton />;

  if (empty || !data) {
    return (
      <div className="text-center py-24">
        <div className="text-6xl mb-4">📂</div>
        <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">{t("dashboard.noData")}</h2>
        <p className="text-gray-500 mt-2">{t("dashboard.noDataBody")}</p>
        <Link href="/upload" className="mt-6 inline-block px-6 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">
          {t("dashboard.noDataCta")}
        </Link>
      </div>
    );
  }

  const { health, primary_month, secondary_month, primary_is_current, days_since_last_update, last_transaction_date, current_balance, current_balance_date } = data;
  const monthCount = health.months_analyzed.length;
  const txCount = health.summary.transaction_count;
  const rangeStart = health.months_analyzed[0];
  const rangeEnd = health.months_analyzed[health.months_analyzed.length - 1];
  const primaryLabel = primary_is_current
    ? t("dashboard.primaryLabelCurrent", { month: primary_month.month })
    : t("dashboard.primaryLabelFull", { month: primary_month.month });
  const secondaryLabel = primary_is_current
    ? t("dashboard.secondaryLabelPrev", { month: secondary_month?.month ?? "" })
    : t("dashboard.secondaryLabelPartial", { month: secondary_month?.month ?? "" });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("dashboard.title")}</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
          {t("dashboard.subtitle", { months: monthCount, txCount, rangeStart, rangeEnd })}
        </p>
      </div>
      <StalenessAlert days={days_since_last_update} lastDate={last_transaction_date} />

      {/* Global snapshot — score + balance: data about the account as a whole, not month-specific */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="md:col-span-1"><ScoreDial score={health.overall_score} grade={health.grade} /></div>
        {current_balance != null && (
          <div className="md:col-span-1">
            <MetricCard
              label={t("dashboard.labelBalance")}
              value={formatEur(current_balance)}
              sub={current_balance_date ? t("dashboard.labelBalanceAs", { date: formatDate(current_balance_date, intlLocale) }) : undefined}
              highlight
            />
          </div>
        )}
      </div>

      {/* Primary month analysis */}
      <div className="space-y-2">
        <div className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wide font-medium pl-1">{primaryLabel}</div>
        <PrimaryMonthCards m={primary_month} isCurrentMonth={primary_is_current} />
      </div>
      {secondary_month && <SecondaryMonthStrip m={secondary_month} label={secondaryLabel} />}
      <AlertBanner alerts={health.alerts} />
      {recentTxs.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-700 dark:text-gray-300 text-sm uppercase tracking-wide">{t("dashboard.recentTitle")}</h3>
            <Link href="/transactions" className="text-xs text-indigo-600 hover:underline font-medium">{t("dashboard.recentLink")}</Link>
          </div>
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {recentTxs.map((tx) => (
                  <tr key={tx.id} className={`hover:bg-gray-50 dark:hover:bg-gray-800 ${tx.is_reversal ? "opacity-50" : ""}`}>
                    <td className="px-4 py-2.5 text-gray-400 whitespace-nowrap w-24">{formatDate(tx.date, intlLocale)}</td>
                    <td className="px-4 py-2.5 text-gray-800 dark:text-gray-200 max-w-xs" title={tx.description}>
                      {tx.clean_description
                        ? <span className="font-medium">{tx.clean_description}</span>
                        : <span className="text-gray-500 dark:text-gray-400 truncate block">{tx.description}</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      {tx.category && (
                        <span className="px-2 py-0.5 rounded-full text-xs bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 font-medium whitespace-nowrap">
                          {tx.subcategory ?? tx.category}
                        </span>
                      )}
                    </td>
                    <td className={`px-4 py-2.5 text-right font-medium tabular-nums whitespace-nowrap ${tx.amount < 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>
                      {formatEur(tx.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <CompactRuleGrid rules={health.rules} />
      <div className="text-xs text-gray-400 dark:text-gray-500 text-right">{t("dashboard.footer")}</div>
    </div>
  );
}
