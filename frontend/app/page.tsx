// app/page.tsx — Dashboard

import { api, MonthSummaryForDashboard } from "@/lib/api";
import { formatEur, STATUS_COLORS } from "@/lib/utils";
import Link from "next/link";

export const dynamic = "force-dynamic";

// ---------------------------------------------------------------------------
// Staleness banner
// ---------------------------------------------------------------------------

function StalenessAlert({ days, lastDate }: { days: number; lastDate: string | null }) {
  if (!lastDate || days < 7) return null;

  const isOld = days >= 30;
  const weeks = Math.floor(days / 7);
  const months = Math.floor(days / 30);

  const label = isOld
    ? `Data is ${months} month${months > 1 ? "s" : ""} old`
    : `Last updated ${weeks} week${weeks > 1 ? "s" : ""} ago`;

  const detail = isOld
    ? "Your analysis may not reflect your current financial situation. Consider importing a fresh statement."
    : "Import a new statement to keep your analysis current.";

  const styles = isOld
    ? "bg-red-50 border-red-200 text-red-800"
    : "bg-yellow-50 border-yellow-200 text-yellow-800";

  const icon = isOld ? "🔴" : "🟡";

  return (
    <div className={`flex gap-3 items-start p-4 rounded-xl border text-sm ${styles}`}>
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div>
        <span className="font-semibold">{label}</span>
        <span className="opacity-80"> — {detail}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Score dial
// ---------------------------------------------------------------------------

function ScoreDial({ score, grade }: { score: number; grade: string }) {
  const color =
    score >= 80 ? "text-green-600" : score >= 55 ? "text-yellow-600" : "text-red-600";
  return (
    <div className="flex flex-col items-center justify-center p-8 bg-white rounded-2xl border border-gray-200 shadow-sm h-full">
      <div className={`text-7xl font-black tabular-nums ${color}`}>{score}</div>
      <div className="text-gray-400 text-sm mt-1">out of 100</div>
      <div className={`mt-3 text-4xl font-bold ${color}`}>Grade {grade}</div>
      <div className="text-gray-500 text-sm mt-2">Financial Health</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metric card
// ---------------------------------------------------------------------------

function MetricCard({
  label,
  value,
  sub,
  highlight,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
  tone?: "positive" | "negative" | "neutral";
}) {
  const valueColor =
    tone === "positive"
      ? "text-green-700"
      : tone === "negative"
      ? "text-red-600"
      : "text-gray-900";

  return (
    <div
      className={`rounded-xl border p-5 shadow-sm ${
        highlight ? "bg-indigo-50 border-indigo-200" : "bg-white border-gray-200"
      }`}
    >
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${valueColor}`}>{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Primary month cards — the main focus of the dashboard
// ---------------------------------------------------------------------------

function PrimaryMonthCards({
  m,
  isCurrentMonth,
}: {
  m: MonthSummaryForDashboard;
  isCurrentMonth: boolean;
}) {
  const leisureTone: "positive" | "negative" | "neutral" =
    m.leisure_remaining > 0 ? "positive" : "negative";

  const savingsTone: "positive" | "negative" | "neutral" =
    m.net_savings > 0 ? "positive" : "negative";

  // Pace card only for partial current month
  const showPace =
    isCurrentMonth &&
    m.days_elapsed != null &&
    m.days_in_month != null &&
    m.projected_month_end_expenses != null;

  const paceTone: "positive" | "negative" | "neutral" =
    m.projected_month_end_expenses != null && m.total_income > 0
      ? m.projected_month_end_expenses < m.total_income
        ? "positive"
        : "negative"
      : "neutral";

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
      {/* Balance */}
      {m.last_balance != null && (
        <MetricCard
          label="Current Balance"
          value={formatEur(m.last_balance)}
          sub={`as of ${m.last_balance_date}`}
          highlight
        />
      )}

      {/* Income this month */}
      <MetricCard
        label={isCurrentMonth ? "Income so far" : "Income"}
        value={formatEur(m.total_income)}
        tone="positive"
      />

      {/* Expenses */}
      <MetricCard
        label={isCurrentMonth ? "Spent so far" : "Expenses"}
        value={formatEur(m.total_expenses)}
        tone="negative"
      />

      {/* Savings */}
      <MetricCard
        label={isCurrentMonth ? "Net this month" : "Net savings"}
        value={formatEur(m.net_savings)}
        sub={m.drew_from_savings ? "⚠ drew from savings" : undefined}
        tone={savingsTone}
      />

      {/* Leisure remaining */}
      <MetricCard
        label="Leisure budget left"
        value={formatEur(m.leisure_remaining)}
        sub={`${formatEur(m.leisure_spent)} of ${formatEur(m.leisure_budget)} used`}
        tone={leisureTone}
      />

      {/* Pace / projection */}
      {showPace && (
        <MetricCard
          label="Month-end projection"
          value={formatEur(m.projected_month_end_expenses!)}
          sub={`day ${m.days_elapsed} of ${m.days_in_month} · ${m.days_of_data}d of data`}
          tone={paceTone}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Secondary month strip — compact row for the "other" month
// ---------------------------------------------------------------------------

function SecondaryMonthStrip({
  m,
  label,
}: {
  m: MonthSummaryForDashboard;
  label: string;
}) {
  return (
    <div className="bg-gray-50 rounded-xl border border-gray-200 px-5 py-3">
      <div className="text-xs text-gray-400 uppercase tracking-wide mb-2">{label}</div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="text-gray-500">
          Income <span className="font-semibold text-gray-800">{formatEur(m.total_income)}</span>
        </span>
        <span className="text-gray-500">
          Expenses <span className="font-semibold text-red-600">{formatEur(m.total_expenses)}</span>
        </span>
        <span className="text-gray-500">
          Net{" "}
          <span className={`font-semibold ${m.net_savings >= 0 ? "text-green-700" : "text-red-600"}`}>
            {formatEur(m.net_savings)}
          </span>
          {m.drew_from_savings && <span className="ml-1 text-yellow-600">⚠</span>}
        </span>
        <span className="text-gray-500">
          Leisure left{" "}
          <span className={`font-semibold ${m.leisure_remaining >= 0 ? "text-green-700" : "text-red-600"}`}>
            {formatEur(m.leisure_remaining)}
          </span>
        </span>
        {m.days_of_data > 0 && m.days_of_data < 15 && (
          <span className="text-gray-400 italic">({m.days_of_data}d of data)</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

function AlertBanner({
  alerts,
}: {
  alerts: { rule_id: string; name: string; status: string; message: string }[];
}) {
  if (!alerts.length) return null;
  return (
    <div className="space-y-2">
      <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
        Prioritized Alerts
      </h3>
      {alerts.map((a) => (
        <div
          key={a.rule_id}
          className={`flex gap-3 p-3 rounded-lg border text-sm ${STATUS_COLORS[a.status]}`}
        >
          <span>{a.status === "red" ? "🔴" : "🟡"}</span>
          <div>
            <span className="font-semibold">{a.name}:</span> {a.message}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rule card
// ---------------------------------------------------------------------------

function RuleCard({
  rule,
}: {
  rule: { rule_id: string; name: string; status: string; score: number; message: string };
}) {
  const badgeColor =
    rule.status === "green"
      ? "bg-green-100 text-green-800"
      : rule.status === "amber"
      ? "bg-yellow-100 text-yellow-800"
      : "bg-red-100 text-red-800";
  return (
    <div className={`p-4 rounded-xl border ${STATUS_COLORS[rule.status]}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-sm">{rule.name}</div>
          <div className="text-xs mt-1 opacity-80">{rule.message}</div>
        </div>
        <div className="text-right shrink-0">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeColor}`}>
            {rule.status.toUpperCase()}
          </span>
          <div className="text-lg font-bold mt-1">{rule.score.toFixed(0)}</div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function DashboardPage() {
  let data: Awaited<ReturnType<typeof api.dashboard>>;
  try {
    data = await api.dashboard();
  } catch {
    return (
      <div className="text-center py-24">
        <div className="text-6xl mb-4">📂</div>
        <h2 className="text-xl font-semibold text-gray-700">No data yet</h2>
        <p className="text-gray-500 mt-2">Upload your bank statement to get started.</p>
        <Link
          href="/upload"
          className="mt-6 inline-block px-6 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700"
        >
          Upload Statement
        </Link>
      </div>
    );
  }

  const { health, primary_month, secondary_month, primary_is_current, days_since_last_update, last_transaction_date } = data;

  // Header subtitle: "7 months · 342 transactions"
  const monthCount = health.months_analyzed.length;
  const txCount = health.summary.transaction_count;
  const rangeStart = health.months_analyzed[0];
  const rangeEnd = health.months_analyzed[health.months_analyzed.length - 1];

  // Label for primary/secondary sections
  const primaryLabel = primary_is_current
    ? `This month — ${primary_month.month}`
    : `Last full month — ${primary_month.month}`;
  const secondaryLabel = primary_is_current
    ? `Previous month — ${secondary_month?.month}`
    : `Current month (partial) — ${secondary_month?.month}`;

  // Recent transactions
  let recentTxs: Awaited<ReturnType<typeof api.transactions>>["items"] = [];
  try {
    const txData = await api.transactions({ limit: 8 });
    recentTxs = txData.items;
  } catch {
    // non-critical
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">
          {monthCount} months · {txCount} transactions &nbsp;·&nbsp; {rangeStart} → {rangeEnd}
        </p>
      </div>

      {/* Staleness alert */}
      <StalenessAlert days={days_since_last_update} lastDate={last_transaction_date} />

      {/* Score + primary month cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="md:col-span-1">
          <ScoreDial score={health.overall_score} grade={health.grade} />
        </div>
        <div className="md:col-span-3 space-y-2">
          <div className="text-xs text-gray-400 uppercase tracking-wide font-medium pl-1">
            {primaryLabel}
          </div>
          <PrimaryMonthCards m={primary_month} isCurrentMonth={primary_is_current} />
        </div>
      </div>

      {/* Secondary month strip */}
      {secondary_month && (
        <SecondaryMonthStrip m={secondary_month} label={secondaryLabel} />
      )}

      {/* Prioritized alerts */}
      <AlertBanner alerts={health.alerts} />

      {/* Recent transactions */}
      {recentTxs.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
              Recent Transactions
            </h3>
            <Link
              href="/transactions"
              className="text-xs text-indigo-600 hover:underline font-medium"
            >
              View all →
            </Link>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-gray-100">
                {recentTxs.map((tx) => (
                  <tr
                    key={tx.id}
                    className={`hover:bg-gray-50 ${tx.is_reversal ? "opacity-50" : ""}`}
                  >
                    <td className="px-4 py-2.5 text-gray-400 whitespace-nowrap w-24">{tx.date}</td>
                    <td className="px-4 py-2.5 text-gray-800 max-w-xs" title={tx.description}>
                      {tx.clean_description ? (
                        <span className="font-medium">{tx.clean_description}</span>
                      ) : (
                        <span className="text-gray-500 truncate block">{tx.description}</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {tx.category && (
                        <span className="px-2 py-0.5 rounded-full text-xs bg-indigo-50 text-indigo-700 font-medium whitespace-nowrap">
                          {tx.subcategory ?? tx.category}
                        </span>
                      )}
                    </td>
                    <td
                      className={`px-4 py-2.5 text-right font-medium tabular-nums whitespace-nowrap ${
                        tx.amount < 0 ? "text-red-600" : "text-green-600"
                      }`}
                    >
                      {formatEur(tx.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Rule-by-rule breakdown */}
      <div>
        <h3 className="font-semibold text-gray-700 text-sm uppercase tracking-wide mb-3">
          Rule-by-Rule Breakdown
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {health.rules.map((rule) => (
            <RuleCard key={rule.rule_id} rule={rule} />
          ))}
        </div>
      </div>

      <div className="text-xs text-gray-400 text-right">All data is stored locally. No external calls.</div>
    </div>
  );
}
